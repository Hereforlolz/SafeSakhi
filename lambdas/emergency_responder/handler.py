import json
import boto3
import logging
from datetime import datetime
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
s3 = boto3.client('s3')

def lambda_handler(event, context):
    """
    Enhanced emergency response handler with better error handling and location intelligence
    """
    try:
        # Enhanced input validation
        if 'body' in event:
            # API Gateway format
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            # Direct invocation format
            body = event
        
        # Validate required fields
        required_fields = ['user_id', 'risk_assessment', 'emergency_type', 'timestamp']
        for field in required_fields:
            if field not in body:
                logger.error(f"Missing required field: {field}")
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': f'Missing required field: {field}'})
                }
        
        user_id = body['user_id']
        risk_assessment = body['risk_assessment']
        emergency_type = body['emergency_type']
        timestamp = body['timestamp']
        location = body.get('location', {})
        
        logger.info(f"Processing emergency response for user {user_id}")
        
        # Get user profile (with fallback if user doesn't exist)
        user_profile = get_user_profile(user_id)
        emergency_contacts = user_profile.get('emergency_contacts', [])
        preferences = user_profile.get('emergency_preferences', {})
        
        # Use provided location or fall back to user's last known location
        current_location = location if location else user_profile.get('last_known_location', {})
        
        # Execute emergency response (simplified for now)
        response_actions = execute_emergency_response(
            user_id, risk_assessment, emergency_contacts, preferences, current_location
        )
        
        # Log the emergency event
        log_emergency_event(user_id, risk_assessment, response_actions, timestamp, current_location)
        
        logger.info(f"Emergency response completed for user {user_id}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'emergency_response_initiated': True,
                'actions_taken': response_actions,
                'current_location': current_location,
                'timestamp': timestamp,
                'user_id': user_id
            })
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON format'})
        }
    except Exception as e:
        logger.error(f"Error in emergency response: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Emergency response failed',
                'details': str(e)
            })
        }

def get_user_profile(user_id):
    """Get user profile with emergency contacts"""
    try:
        table_name = os.environ.get('USERS_TABLE_NAME', 'SafeSakhi-Users')
        table = dynamodb.Table(table_name)
        
        response = table.get_item(Key={'user_id': user_id})
        
        if 'Item' not in response:
            # Create a basic user profile if it doesn't exist
            logger.info(f"User {user_id} not found, creating basic profile")
            basic_profile = {
                'user_id': user_id,
                'emergency_contacts': [
                    {
                        'name': 'Emergency Contact',
                        'method': 'sms',
                        'value': '+1234567890'  # Default emergency number
                    }
                ],
                'emergency_preferences': {
                    'auto_notify_authorities': False,
                    'emergency_location_sharing': True
                },
                'created_at': int(datetime.now().timestamp())
            }
            
            table.put_item(Item=basic_profile)
            return basic_profile
        
        return response['Item']
        
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        # Return minimal profile to prevent complete failure
        return {
            'user_id': user_id,
            'emergency_contacts': [],
            'emergency_preferences': {
                'auto_notify_authorities': False,
                'emergency_location_sharing': True
            }
        }

def execute_emergency_response(user_id, risk_assessment, emergency_contacts, preferences, current_location):
    """Execute emergency response actions"""
    actions_taken = []
    
    try:
        # 1. Send alerts to emergency contacts
        if emergency_contacts:
            alert_results = send_emergency_alerts(
                user_id, risk_assessment, emergency_contacts, current_location
            )
            actions_taken.extend(alert_results)
        else:
            logger.warning(f"No emergency contacts found for user {user_id}")
            actions_taken.append("No emergency contacts configured")
        
        # 2. Start evidence collection
        evidence_id = start_evidence_collection(user_id, risk_assessment, current_location)
        if evidence_id:
            actions_taken.append(f"Evidence collection started: {evidence_id}")
        
        # 3. Enable location tracking if preferences allow
        if preferences.get('emergency_location_sharing', True):
            tracking_result = enable_location_tracking(user_id, current_location)
            if tracking_result:
                actions_taken.append("Enhanced location tracking enabled")
        
        # 4. Send SNS notification
        sns_result = send_sns_notification(user_id, risk_assessment, current_location)
        if sns_result:
            actions_taken.append("SNS emergency notification sent")
        
        return actions_taken
        
    except Exception as e:
        logger.error(f"Error executing emergency response: {str(e)}")
        return [f"Error: {str(e)}"]

def send_emergency_alerts(user_id, risk_assessment, emergency_contacts, current_location):
    """Send alerts to emergency contacts"""
    sent_alerts = []
    
    try:
        risk_level = risk_assessment.get('risk_level', 'HIGH')
        timestamp = datetime.fromtimestamp(risk_assessment.get('timestamp', 0))
        
        # Create alert message
        message = create_alert_message(user_id, risk_level, timestamp, current_location)
        
        for contact in emergency_contacts:
            try:
                contact_method = contact.get('method', 'sms')
                contact_value = contact.get('value')
                contact_name = contact.get('name', 'Contact')
                
                if not contact_value:
                    continue
                
                if contact_method == 'sms':
                    # Send SMS via SNS
                    response = sns.publish(
                        PhoneNumber=contact_value,
                        Message=message[:160],  # SMS character limit
                        Subject='SafeSakhi Emergency Alert'
                    )
                    sent_alerts.append(f"SMS sent to {contact_name}")
                    logger.info(f"SMS sent to {contact_name}: {response['MessageId']}")
                    
                elif contact_method == 'email':
                    # Send email via SNS topic
                    topic_arn = os.environ.get('SNS_TOPIC_ARN')
                    if topic_arn:
                        response = sns.publish(
                            TopicArn=topic_arn,
                            Message=message,
                            Subject='SafeSakhi Emergency Alert'
                        )
                        sent_alerts.append(f"Email sent to {contact_name}")
                        logger.info(f"Email sent to {contact_name}: {response['MessageId']}")
                
            except Exception as e:
                logger.error(f"Error sending alert to {contact.get('name', 'contact')}: {str(e)}")
                sent_alerts.append(f"Failed to send alert to {contact.get('name', 'contact')}")
        
        return sent_alerts
        
    except Exception as e:
        logger.error(f"Error sending emergency alerts: {str(e)}")
        return [f"Alert error: {str(e)}"]

def create_alert_message(user_id, risk_level, timestamp, current_location):
    """Create emergency alert message"""
    message = f"""🚨 SAFESAKHI EMERGENCY ALERT 🚨

Risk Level: {risk_level}
Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
User: {user_id}
"""
    
    if current_location and current_location.get('lat') and current_location.get('lng'):
        lat = current_location['lat']
        lng = current_location['lng']
        message += f"\n📍 Location: {lat}, {lng}"
        message += f"\nMaps: https://maps.google.com/?q={lat},{lng}"
    
    message += "\n\nPlease check on the user immediately."
    
    return message

def send_sns_notification(user_id, risk_assessment, current_location):
    """Send SNS notification to emergency topic"""
    try:
        topic_arn = os.environ.get('SNS_TOPIC_ARN')
        if not topic_arn:
            logger.warning("SNS_TOPIC_ARN not configured")
            return False
        
        message = {
            'user_id': user_id,
            'risk_assessment': risk_assessment,
            'current_location': current_location,
            'timestamp': datetime.now().isoformat(),
            'event_type': 'emergency_response'
        }
        
        response = sns.publish(
            TopicArn=topic_arn,
            Message=json.dumps(message),
            Subject=f'SafeSakhi Emergency - User {user_id}'
        )
        
        logger.info(f"SNS notification sent: {response['MessageId']}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending SNS notification: {str(e)}")
        return False

def start_evidence_collection(user_id, risk_assessment, current_location):
    """Start collecting evidence"""
    try:
        evidence_id = f"{user_id}-{int(datetime.now().timestamp())}-emergency"
        
        evidence_table_name = os.environ.get('EVIDENCE_TABLE_NAME', 'SafeSakhi-Evidence')
        evidence_table = dynamodb.Table(evidence_table_name)
        
        evidence_table.put_item(
            Item={
                'evidence_id': evidence_id,
                'user_id': user_id,
                'timestamp': risk_assessment.get('timestamp', int(datetime.now().timestamp())),
                'evidence_type': 'emergency_context',
                'risk_assessment': risk_assessment,
                'current_location': current_location,
                'collection_active': True,
                'created_at': int(datetime.now().timestamp()),
                'retention_until': int((datetime.now().timestamp() + (90 * 24 * 60 * 60)))  # 90 days
            }
        )
        
        logger.info(f"Evidence collection started: {evidence_id}")
        return evidence_id
        
    except Exception as e:
        logger.error(f"Error starting evidence collection: {str(e)}")
        return None

def enable_location_tracking(user_id, current_location):
    """Enable enhanced location tracking"""
    try:
        tracking_table_name = os.environ.get('LOCATION_TRACKING_TABLE_NAME', 'SafeSakhi-LocationTracking')
        tracking_table = dynamodb.Table(tracking_table_name)
        
        tracking_table.put_item(
            Item={
                'user_id': user_id,
                'timestamp': int(datetime.now().timestamp()),
                'tracking_enabled': True,
                'emergency_mode': True,
                'current_location': current_location,
                'started_at': int(datetime.now().timestamp()),
                'update_interval': 30,  # seconds
                'high_accuracy': True
            }
        )
        
        logger.info(f"Location tracking enabled for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error enabling location tracking: {str(e)}")
        return False

def log_emergency_event(user_id, risk_assessment, response_actions, timestamp, current_location):
    """Log emergency event"""
    try:
        incident_table_name = os.environ.get('INCIDENT_HISTORY_TABLE_NAME', 'SafeSakhi-IncidentHistory')
        incident_table = dynamodb.Table(incident_table_name)
        
        incident_table.put_item(
            Item={
                'user_id': user_id,
                'created_at': int(datetime.now().timestamp()),
                'event_id': f"{user_id}-emergency-{timestamp}",
                'timestamp': timestamp,
                'risk_assessment': risk_assessment,
                'response_actions': response_actions,
                'current_location': current_location,
                'event_type': 'emergency_response',
                'status': 'active'
            }
        )
        
        logger.info(f"Emergency event logged for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error logging emergency event: {str(e)}")