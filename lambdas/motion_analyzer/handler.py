import json
import os
import boto3
import logging
from datetime import datetime
from decimal import Decimal

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# DynamoDB Table Name from Environment Variable
MOTION_ANALYSIS_TABLE_NAME = os.environ.get('MOTION_ANALYSIS_TABLE_NAME')
motion_analysis_table = dynamodb.Table(MOTION_ANALYSIS_TABLE_NAME)

# Risk Assessment Lambda Name
RISK_ASSESSMENT_LAMBDA_NAME = os.environ.get('RISK_ASSESSMENT_LAMBDA_NAME')

# Environment Variables for Analysis Thresholds (from template.yaml)
THREAT_SCORE_TRIGGER_THRESHOLD = float(os.environ.get('THREAT_SCORE_TRIGGER_THRESHOLD', '0.5'))
MOTION_ACTIVITY_THRESHOLD = float(os.environ.get('MOTION_ACTIVITY_THRESHOLD', '0.1'))
LOCATION_STATIONARY_THRESHOLD_METERS = float(os.environ.get('LOCATION_STATIONARY_THRESHOLD_METERS', '50'))
STATIONARY_DURATION_SECONDS = int(os.environ.get('STATIONARY_DURATION_SECONDS', '300'))


def get_cors_headers():
    """Get standard CORS headers"""
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }


def decimal_default(obj):
    """Helper function to convert float to Decimal for DynamoDB"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    return obj


def calculate_motion_threat_score(motion_activity, is_stationary, location_accuracy=None):
    """
    Calculates a threat score based on motion and location data.
    This is a simplified example.
    """
    score = 0.0

    # High motion activity could indicate struggle or rapid movement
    if motion_activity > MOTION_ACTIVITY_THRESHOLD:
        score += motion_activity * 0.4

    # Being stationary in an unexpected location or for too long
    if is_stationary:
        score += 0.3 # Base score for being stationary

        # If location accuracy is poor while stationary, increase threat
        if location_accuracy and location_accuracy > LOCATION_STATIONARY_THRESHOLD_METERS:
            score += 0.2

        # In a real app, you'd check stationary duration and known safe locations

    # Ensure score is between 0 and 1
    return min(1.0, max(0.0, score))


def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # API Gateway Proxy Integration puts the body as a string under 'body' key
        if 'body' in event and event['body'] is not None:
            body_data = json.loads(event['body'])
        else:
            body_data = event # For direct Lambda invocation or other triggers

        logger.info(f"Parsed body data: {json.dumps(body_data)}")

        user_id = body_data.get('user_id')
        created_at_epoch = body_data.get('created_at_epoch')
        motion_activity = body_data.get('motion_activity')
        location = body_data.get('location') # This will be a dictionary
        is_stationary = body_data.get('is_stationary')

        if not all([user_id, created_at_epoch, motion_activity is not None, location, is_stationary is not None]):
            logger.error("Validation Error: Missing required fields (user_id, created_at_epoch, motion_activity, location, is_stationary).")
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),  # Added CORS headers
                'body': json.dumps({'error': 'Missing required fields for motion analysis'})
            }

        # Convert timestamp to integer if it's not already
        try:
            created_at_epoch = int(created_at_epoch)
        except ValueError:
            logger.error(f"Invalid created_at_epoch format: {created_at_epoch}")
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),  # Added CORS headers
                'body': json.dumps({'error': 'Invalid created_at_epoch format. Must be an integer epoch.'})
            }

        # Extract location details
        latitude = location.get('latitude')
        longitude = location.get('longitude')
        accuracy = location.get('accuracy')

        if not all([user_id, created_at_epoch]):
            logger.error("Validation Error: Missing required fields (user_id, timestamp).")
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),  # Added CORS headers
                'body': json.dumps({'error': 'Missing required fields (user_id, timestamp)'})
            }

        # Calculate threat score
        threat_score = calculate_motion_threat_score(motion_activity, is_stationary, accuracy)

        # Store analysis in DynamoDB - Convert floats to Decimal for DynamoDB
        item = {
            'user_id': user_id,
            'created_at_epoch': created_at_epoch,
            'motion_activity': Decimal(str(motion_activity)),
            'location': {
                'latitude': Decimal(str(latitude)),
                'longitude': Decimal(str(longitude)),
                'accuracy': Decimal(str(accuracy)) if accuracy is not None else None
            },
            'is_stationary': is_stationary,
            'threat_score': Decimal(str(threat_score)),
            'analysis_time': datetime.utcnow().isoformat()
        }
        
        # Remove None values from location
        item['location'] = {k: v for k, v in item['location'].items() if v is not None}
        
        motion_analysis_table.put_item(Item=item)
        logger.info(f"Motion analysis stored for user {user_id} at {created_at_epoch} with score {threat_score}")

        # Invoke Risk Assessor Lambda if threat score exceeds threshold
        if threat_score >= THREAT_SCORE_TRIGGER_THRESHOLD:
            logger.info(f"Threat score {threat_score} >= threshold {THREAT_SCORE_TRIGGER_THRESHOLD}. Invoking Risk Assessor.")
            lambda_client.invoke(
                FunctionName=RISK_ASSESSMENT_LAMBDA_NAME,
                InvocationType='Event',  # Asynchronous invocation
                Payload=json.dumps({
                    'user_id': user_id,
                    'trigger_type': 'motion_analysis',
                    'timestamp': created_at_epoch, # Use motion timestamp for consistency
                    'threat_score': threat_score
                })
            )
            logger.info("Risk Assessor Lambda invoked.")

        return {
            'statusCode': 200,
            'headers': get_cors_headers(),  # Added CORS headers
            'body': json.dumps({'message': 'Motion analysis processed successfully', 'threat_score': threat_score})
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return {
            'statusCode': 400,
            'headers': get_cors_headers(),  # Added CORS headers
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except KeyError as e:
        logger.error(f"Missing expected key in event body or location data: {e}")
        return {
            'statusCode': 400,
            'headers': get_cors_headers(),  # Added CORS headers
            'body': json.dumps({'error': f'Missing expected key: {e}'})
        }
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),  # Added CORS headers
            'body': json.dumps({'error': 'Internal server error'})
        }