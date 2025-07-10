import json
import os
import boto3
import logging
from datetime import datetime, timedelta

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# DynamoDB Table Names from Environment Variables
USERS_TABLE_NAME = os.environ.get('USERS_TABLE_NAME')
AUDIO_ANALYSIS_TABLE_NAME = os.environ.get('AUDIO_ANALYSIS_TABLE_NAME')
MOTION_ANALYSIS_TABLE_NAME = os.environ.get('MOTION_ANALYSIS_TABLE_NAME')
TEXT_ANALYSIS_TABLE_NAME = os.environ.get('TEXT_ANALYSIS_TABLE_NAME')
RISK_ASSESSMENTS_TABLE_NAME = os.environ.get('RISK_ASSESSMENTS_TABLE_NAME')
INCIDENT_HISTORY_TABLE_NAME = os.environ.get('INCIDENT_HISTORY_TABLE_NAME')

users_table = dynamodb.Table(USERS_TABLE_NAME)
audio_analysis_table = dynamodb.Table(AUDIO_ANALYSIS_TABLE_NAME)
motion_analysis_table = dynamodb.Table(MOTION_ANALYSIS_TABLE_NAME)
text_analysis_table = dynamodb.Table(TEXT_ANALYSIS_TABLE_NAME)
risk_assessments_table = dynamodb.Table(RISK_ASSESSMENTS_TABLE_NAME)
incident_history_table = dynamodb.Table(INCIDENT_HISTORY_TABLE_NAME)

# Emergency Response Lambda Name
EMERGENCY_RESPONSE_LAMBDA_NAME = os.environ.get('EMERGENCY_RESPONSE_LAMBDA_NAME')

# Environment Variables for Risk Assessment Logic
RISK_ASSESSMENT_THRESHOLD = float(os.environ.get('RISK_ASSESSMENT_THRESHOLD', '0.8'))
RECENT_THREATS_TIME_WINDOW_SECONDS = int(os.environ.get('RECENT_THREATS_TIME_WINDOW_SECONDS', '1800')) # 30 minutes

# Weights for different risk components
WEIGHT_BASE_SCORE = float(os.environ.get('WEIGHT_BASE_SCORE', '0.4'))
WEIGHT_ESCALATION_SCORE = float(os.environ.get('WEIGHT_ESCALATION_SCORE', '0.3'))
WEIGHT_CONTEXT_SCORE = float(os.environ.get('WEIGHT_CONTEXT_SCORE', '0.2'))
WEIGHT_PATTERN_SCORE = float(os.environ.get('WEIGHT_PATTERN_SCORE', '0.1'))

# Thresholds for risk levels
THRESHOLD_CRITICAL = float(os.environ.get('THRESHOLD_CRITICAL', '0.9'))
THRESHOLD_HIGH = float(os.environ.get('THRESHOLD_HIGH', '0.7'))
THRESHOLD_MEDIUM = float(os.environ.get('THRESHOLD_MEDIUM', '0.5'))
THRESHOLD_LOW = float(os.environ.get('THRESHOLD_LOW', '0.3'))

# Contextual factors
CONTEXT_NIGHT_HOURS_BONUS = float(os.environ.get('CONTEXT_NIGHT_HOURS_BONUS', '0.2'))
CONTEXT_HIGH_RISK_AREA_BONUS = float(os.environ.get('CONTEXT_HIGH_RISK_AREA_BONUS', '0.3'))
CONTEXT_ISOLATED_LOCATION_BONUS = float(os.environ.get('CONTEXT_ISOLATED_LOCATION_BONUS', '0.1'))
LOCATION_ACCURACY_THRESHOLD_METERS = float(os.environ.get('LOCATION_ACCURACY_THRESHOLD_METERS', '100'))
HIGH_RISK_AREA_PROXIMITY_DEGREE = float(os.environ.get('HIGH_RISK_AREA_PROXIMITY_DEGREE', '0.01')) # Approx 1.1km at equator per 0.01 degree

# Escalation factors
ESCALATION_MULTI_TYPE_BONUS = float(os.environ.get('ESCALATION_MULTI_TYPE_BONUS', '0.4'))
ESCALATION_HIGH_COUNT_BONUS = float(os.environ.get('ESCALATION_HIGH_COUNT_BONUS', '0.3'))
ESCALATION_HIGH_SEVERITY_BONUS = float(os.environ.get('ESCALATION_HIGH_SEVERITY_BONUS', '0.3'))
ESCALATION_HIGH_SEVERITY_THRESHOLD = float(os.environ.get('ESCALATION_HIGH_SEVERITY_THRESHOLD', '0.6'))
ESCALATION_HIGH_COUNT_THRESHOLD = int(os.environ.get('ESCALATION_HIGH_COUNT_THRESHOLD', '3'))


def get_risk_level(score):
    if score >= THRESHOLD_CRITICAL:
        return 'CRITICAL'
    elif score >= THRESHOLD_HIGH:
        return 'HIGH'
    elif score >= THRESHOLD_MEDIUM:
        return 'MEDIUM'
    elif score >= THRESHOLD_LOW:
        return 'LOW'
    else:
        return 'NONE'

def is_within_high_risk_area(user_location, high_risk_areas):
    """
    Checks if the user's current location is within any defined high-risk areas.
    Simplified: checks if within a square bounding box for now.
    For real-world, use geo-spatial libraries.
    """
    if not user_location or not high_risk_areas:
        return False

    user_lat = user_location.get('latitude')
    user_lon = user_location.get('longitude')
    if user_lat is None or user_lon is None:
        return False

    for area in high_risk_areas:
        area_lat = area.get('latitude')
        area_lon = area.get('longitude')
        area_radius_km = area.get('radius_km') # Not directly used in simple box check, but good to have

        # Simple bounding box check (approximate for degrees)
        # 1 degree of latitude is approx 111 km. 1 degree longitude varies.
        # Using a fixed degree proximity for simplicity now.
        if area_lat is not None and area_lon is not None:
            if (abs(user_lat - area_lat) <= HIGH_RISK_AREA_PROXIMITY_DEGREE and
                abs(user_lon - area_lon) <= HIGH_RISK_AREA_PROXIMITY_DEGREE):
                return True
    return False

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # Risk Assessor is invoked directly by other Lambdas, so 'body' key is not expected
        user_id = event.get('user_id')
        trigger_type = event.get('trigger_type')
        timestamp = event.get('timestamp')
        threat_score = event.get('threat_score')

        if not all([user_id, trigger_type, timestamp, threat_score is not None]):
            logger.error("Validation Error: Missing required fields (user_id, trigger_type, timestamp, threat_score).")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required fields for risk assessment'})
            }

        # Fetch user profile
        user_response = users_table.get_item(Key={'user_id': user_id})
        user_profile = user_response.get('Item')

        if not user_profile:
            logger.warning(f"User profile not found for {user_id}. Cannot perform full risk assessment.")
            # Still store the base threat, but won't trigger emergency if no contacts
            final_score = threat_score * WEIGHT_BASE_SCORE
            risk_level = get_risk_level(final_score)
        else:
            # 1. Base Score (from the triggering analysis)
            base_score = threat_score

            # 2. Escalation Score (based on recent history)
            escalation_score = 0.0
            time_window_start = datetime.fromtimestamp(timestamp) - timedelta(seconds=RECENT_THREATS_TIME_WINDOW_SECONDS)
            time_window_start_epoch = int(time_window_start.timestamp())

            # Query recent analysis data from all relevant tables
            recent_threats_count = 0
            recent_threat_types = set()
            high_severity_threats = 0

            # Query Audio Analysis
            audio_response = audio_analysis_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id) & boto3.dynamodb.conditions.Key('timestamp').gte(time_window_start_epoch)
            )
            for item in audio_response.get('Items', []):
                recent_threats_count += 1
                recent_threat_types.add('audio')
                if item.get('threat_score', 0) >= ESCALATION_HIGH_SEVERITY_THRESHOLD:
                    high_severity_threats += 1

            # Query Motion Analysis
            motion_response = motion_analysis_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id) & boto3.dynamodb.conditions.Key('created_at_epoch').gte(time_window_start_epoch)
            )
            for item in motion_response.get('Items', []):
                recent_threats_count += 1
                recent_threat_types.add('motion')
                if item.get('threat_score', 0) >= ESCALATION_HIGH_SEVERITY_THRESHOLD:
                    high_severity_threats += 1

            # Query Text Analysis
            text_response = text_analysis_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id) & boto3.dynamodb.conditions.Key('timestamp').gte(time_window_start_epoch)
            )
            for item in text_response.get('Items', []):
                recent_threats_count += 1
                recent_threat_types.add('text')
                if item.get('threat_score', 0) >= ESCALATION_HIGH_SEVERITY_THRESHOLD:
                    high_severity_threats += 1

            if len(recent_threat_types) > 1:
                escalation_score += ESCALATION_MULTI_TYPE_BONUS
            if recent_threats_count >= ESCALATION_HIGH_COUNT_THRESHOLD:
                escalation_score += ESCALATION_HIGH_COUNT_BONUS
            if high_severity_threats > 0:
                escalation_score += ESCALATION_HIGH_SEVERITY_BONUS

            # 3. Contextual Score (based on user profile and current conditions)
            context_score = 0.0
            current_hour = datetime.fromtimestamp(timestamp).hour
            if current_hour >= 22 or current_hour < 6: # Night hours (10 PM to 6 AM)
                context_score += CONTEXT_NIGHT_HOURS_BONUS

            # Check if user is in a high-risk area (requires location data from motion/text/audio if available)
            user_current_location = None
            if trigger_type == 'motion_analysis' and event.get('location'):
                user_current_location = event.get('location')
            # In a more complex system, you'd fetch the latest known location from a user's status table

            if user_current_location and user_profile.get('high_risk_areas'):
                if is_within_high_risk_area(user_current_location, user_profile['high_risk_areas']):
                    context_score += CONTEXT_HIGH_RISK_AREA_BONUS

            # Add bonus for isolated location (if inferred, e.g., from lack of network/GPS signal, or known remote areas)
            # This would require more sophisticated logic, but adding a placeholder
            # if user_profile.get('is_isolated_location', False):
            #     context_score += CONTEXT_ISOLATED_LOCATION_BONUS

            # 4. Pattern Recognition Score (more advanced, placeholder for now)
            pattern_score = 0.0
            # This would involve looking for sequences of events, specific timing, etc.

            # Combine scores with weights
            final_score = (base_score * WEIGHT_BASE_SCORE) + \
                          (escalation_score * WEIGHT_ESCALATION_SCORE) + \
                          (context_score * WEIGHT_CONTEXT_SCORE) + \
                          (pattern_score * WEIGHT_PATTERN_SCORE)

            # Ensure final score is within 0-1 range
            final_score = min(1.0, max(0.0, final_score))
            risk_level = get_risk_level(final_score)

            logger.info(f"Risk assessment for {user_id}: Base={base_score:.2f}, Escalation={escalation_score:.2f}, Context={context_score:.2f}, Final={final_score:.2f}, Level={risk_level}")

            # Store risk assessment
            risk_assessments_table.put_item(
                Item={
                    'user_id': user_id,
                    'timestamp': timestamp,
                    'final_score': final_score,
                    'risk_level': risk_level,
                    'trigger_type': trigger_type,
                    'base_threat_score': threat_score,
                    'escalation_score': escalation_score,
                    'context_score': context_score,
                    'pattern_score': pattern_score,
                    'assessment_time': datetime.utcnow().isoformat()
                }
            )
            logger.info(f"Risk assessment stored for user {user_id}.")

            # Invoke Emergency Responder if risk is high enough
            if final_score >= RISK_ASSESSMENT_THRESHOLD:
                logger.info(f"Final risk score {final_score} >= threshold {RISK_ASSESSMENT_THRESHOLD}. Invoking Emergency Responder.")
                lambda_client.invoke(
                    FunctionName=EMERGENCY_RESPONSE_LAMBDA_NAME,
                    InvocationType='Event', # Asynchronous invocation
                    Payload=json.dumps({
                        'user_id': user_id,
                        'risk_level': risk_level,
                        'final_score': final_score,
                        'trigger_type': trigger_type,
                        'timestamp_iso': datetime.fromtimestamp(timestamp).isoformat(),
                        'emergency_contacts': user_profile.get('emergency_contacts', []) # Pass contacts directly
                    })
                )
                logger.info("Emergency Responder Lambda invoked.")

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Risk assessment complete', 'risk_score': final_score, 'risk_level': risk_level})
        }

    except Exception as e:
        logger.error(f"An unexpected error occurred during risk assessment: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error during risk assessment'})
        }
