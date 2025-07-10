import json
import os
import boto3
import logging
from datetime import datetime
from decimal import Decimal
# import numpy # Uncomment if you actually use numpy in your audio processing logic

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
# s3 = boto3.client('s3') # Uncomment if you need to interact with S3 directly in this Lambda
# comprehend = boto3.client('comprehend') # Uncomment if you use Comprehend here
lambda_client = boto3.client('lambda')

# DynamoDB Table Names from Environment Variables
AUDIO_ANALYSIS_TABLE_NAME = os.environ.get('AUDIO_ANALYSIS_TABLE_NAME')
audio_analysis_table = dynamodb.Table(AUDIO_ANALYSIS_TABLE_NAME)

# S3 Bucket Name
AUDIO_TEMP_BUCKET_NAME = os.environ.get('AUDIO_TEMP_BUCKET_NAME')

# Risk Assessment Lambda Name
RISK_ASSESSMENT_LAMBDA_NAME = os.environ.get('RISK_ASSESSMENT_LAMBDA_NAME')

# Environment Variables for Analysis Thresholds (from template.yaml)
THREAT_SCORE_TRIGGER_THRESHOLD = float(os.environ.get('THREAT_SCORE_TRIGGER_THRESHOLD', '0.6'))
COMPREHEND_LANGUAGE_CODE = os.environ.get('COMPREHEND_LANGUAGE_CODE', 'en')
COMPREHEND_SENTIMENT_THRESHOLD = float(os.environ.get('COMPREHEND_SENTIMENT_THRESHOLD', '0.2'))
COMPREHEND_VOLUME_THRESHOLD = float(os.environ.get('COMPREHEND_VOLUME_THRESHOLD', '0.7'))


def calculate_audio_threat_score(volume_level, sentiment_score):
    """
    Calculates a threat score based on audio analysis.
    This is a simplified example. Real audio analysis would be more complex.
    """
    score = 0.0

    # Handle None values
    if volume_level is None:
        volume_level = 0.0
    if sentiment_score is None:
        sentiment_score = 0.0

    # Increase score if volume is high (e.g., shouting)
    if volume_level > COMPREHEND_VOLUME_THRESHOLD:
        score += (volume_level - COMPREHEND_VOLUME_THRESHOLD) * 0.5 # Scale based on how much it exceeds threshold

    # Increase score if sentiment is very negative
    if sentiment_score < -COMPREHEND_SENTIMENT_THRESHOLD: # e.g., if sentiment is -0.7 and threshold is 0.2, -0.7 < -0.2
        score += abs(sentiment_score) * 0.5 # Scale based on how negative it is

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
        audio_data_base64 = body_data.get('audio_data_base64')
        timestamp = body_data.get('timestamp')
        volume_level = body_data.get('volume_level')
        sentiment_score = body_data.get('sentiment_score')
        language_code = body_data.get('language_code')

        if not all([user_id, timestamp]):
            logger.error("Validation Error: Missing required fields (user_id, timestamp).")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required fields (user_id, timestamp)'})
            }

        # Convert timestamp to integer if it's not already
        try:
            timestamp = int(timestamp)
        except ValueError:
            logger.error(f"Invalid timestamp format: {timestamp}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid timestamp format. Must be an integer epoch.'})
            }

        # Calculate threat score
        threat_score = calculate_audio_threat_score(volume_level, sentiment_score)

        # Store analysis in DynamoDB - Convert floats to Decimal
        item = {
            'user_id': user_id,
            'timestamp': timestamp,
            'volume_level': Decimal(str(volume_level)) if volume_level is not None else None,
            'sentiment_score': Decimal(str(sentiment_score)) if sentiment_score is not None else None,
            'language_code': language_code,
            'threat_score': Decimal(str(threat_score)),
            'analysis_time': datetime.utcnow().isoformat()
        }
        audio_analysis_table.put_item(Item=item)
        logger.info(f"Audio analysis stored for user {user_id} at {timestamp} with score {threat_score}")

        # In a real scenario, you might store the audio_data_base64 in S3
        # For this example, we're just processing the metadata.

        # Invoke Risk Assessor Lambda if threat score exceeds threshold
        if threat_score >= THREAT_SCORE_TRIGGER_THRESHOLD:
            logger.info(f"Threat score {threat_score} >= threshold {THREAT_SCORE_TRIGGER_THRESHOLD}. Invoking Risk Assessor.")
            lambda_client.invoke(
                FunctionName=RISK_ASSESSMENT_LAMBDA_NAME,
                InvocationType='Event',  # Asynchronous invocation
                Payload=json.dumps({
                    'user_id': user_id,
                    'trigger_type': 'audio_analysis',
                    'timestamp': timestamp,
                    'threat_score': threat_score
                })
            )
            logger.info("Risk Assessor Lambda invoked.")

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Audio analysis processed successfully', 'threat_score': threat_score})
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except KeyError as e:
        logger.error(f"Missing expected key in event body: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Missing expected key: {e}'})
        }
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }