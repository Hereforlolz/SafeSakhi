import json
import boto3
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
s3 = boto3.client('s3')

def lambda_handler(event, context):
    try:
        user_id = event['user_id']
        risk_assessment = event['risk_assessment']
        emergency_type = event['emergency_type']
        timestamp = event['timestamp']
        
        # Get user's emergency preferences
        user_profile = get_user_profile(user_id)
        emergency_contacts = user_profile.get('emergency_contacts', [])
        preferences = user_profile.get('emergency_preferences', {})
        
        # Execute emergency response
        response_actions = execute_emergency_response(
            user_id, risk_assessment, emergency_contacts, preferences
        )
        
        # Log emergency event
        log_emergency_event(user_id, risk_assessment, response_actions, timestamp)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'emergency_response_initiated': True,
                'actions_taken': response_actions,
                'timestamp': timestamp
            })
        }
        
    except Exception as e:
        logger.error(f"Error in emergency response: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Emergency response failed'})
        }

def get_user_profile(user_id):
    """Get user profile with emergency contacts"""
    try:
        table = dynamodb.Table('SafeSakhi-Users')
        response = table.get_item(Key={'user_id': user_id})
        return response.get('Item', {})
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        return {}

def execute_emergency_response(user_id, risk_assessment, emergency_contacts, preferences):
    """Execute emergency response actions"""
    actions_taken = []
    
    try:
        # 1. Send silent alerts to emergency contacts
        if emergency_contacts:
            sent_alerts = send_emergency_alerts(user_id, risk_assessment, emergency_contacts)
            actions_taken.extend(sent_alerts)
        
        # 2. Start evidence collection
        evidence_id = start_evidence_collection(user_id, risk_assessment)
        if evidence_id:
            actions_taken.append(f"Evidence collection started: {evidence_id}")
        
        # 3. Send location updates
        location_updates = enable_location_tracking(user_id, preferences)
        actions_taken.extend(location_updates)
        
        # 4. Notify authorities if configured
        if preferences.get('auto_notify_authorities', False):
            authority_notification = notify_authorities(user_id, risk_assessment)
            if authority_notification:
                actions_taken.append("Authorities notified")
        
        # 5. Start continuous monitoring
        monitoring_id = start_enhanced_monitoring(user_id)
        if monitoring_id:
            actions_taken.append(f"Enhanced monitoring started: {monitoring_id}")
        
        return actions_taken
        
    except Exception as e:
        logger.error(f"Error executing emergency response: {str(e)}")
        return [f"Error: {str(e)}"]

def send_emergency_alerts(user_id, risk_assessment, emergency_contacts):
    """Send alerts to emergency contacts"""
    sent_alerts = []
    
    try:
        for contact in emergency_contacts:
            contact_method = contact.get('method', 'sms')  # sms, email, call
            contact_value = contact.get('value')
            contact_name = contact.get('name', 'Contact')
            
            if not contact_value:
                continue
            
            # Create alert message
            alert_message = create_alert_message(user_id, risk_assessment, contact_name)
            
            if contact_method == 'sms':
                # Send SMS via SNS
                response = sns.publish(
                    PhoneNumber=contact_value,
                    Message=alert_message,
                    Subject='SafeSakhi Emergency Alert'
                )
                sent_alerts.append(f"SMS sent to {contact_name}")
                
            elif contact_method == 'email':
                # Send email via SNS
                topic_arn = f"arn:aws:sns:us-east-1:123456789012:SafeSakhi-EmergencyAlerts"
                response = sns.publish(
                    TopicArn=topic_arn,
                    Message=alert_message,
                    Subject='SafeSakhi Emergency Alert',
                    MessageAttributes={
                        'email': {
                            'DataType': 'String',
                            'StringValue': contact_value
                        }
                    }
                )
                sent_alerts.append(f"Email sent to {contact_name}")
        
        return sent_alerts
        
    except Exception as e:
        logger.error(f"Error sending alerts: {str(e)}")
        return [f"Alert error: {str(e)}"]

def create_alert_message(user_id, risk_assessment, contact_name):
    """Create emergency alert message"""
    risk_level = risk_assessment.get('risk_level', 'HIGH')
    timestamp = datetime.fromtimestamp(risk_assessment.get('timestamp', 0))
    
    message = f"""
SAFESAKHI EMERGENCY ALERT

Risk Level: {risk_level}
Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
User ID: {user_id}

This is an automated safety alert. The user may be in a potentially dangerous situation.

If this is a real emergency, please:
1. Try to contact the user immediately
2. Consider calling local emergency services
3. Check the SafeSakhi app for location updates

This alert was generated by AI analysis of potential threat indicators.

Reply STOP to unsubscribe from emergency alerts.
"""
    
    return message.strip()

def start_evidence_collection(user_id, risk_assessment):
    """Start collecting evidence for the emergency"""
    try:
        evidence_id = f"{user_id}-{int(datetime.now().timestamp())}-emergency"
        
        # Store emergency context as evidence
        evidence_table = dynamodb.Table('SafeSakhi-Evidence')
        evidence_table.put_item(
            Item={
                'user_id': user_id,
                'evidence_id': evidence_id,
                'timestamp': risk_assessment.get('timestamp'),
                'evidence_type': 'emergency_context',
                'risk_assessment': risk_assessment,
                'collection_active': True,
                'created_at': int(datetime.now().timestamp())
            }
        )
        
        return evidence_id
        
    except Exception as e:
        logger.error(f"Error starting evidence collection: {str(e)}")
        return None

def enable_location_tracking(user_id, preferences):
    """Enable enhanced location tracking during emergency"""
    actions = []
    
    try:
        if preferences.get('emergency_location_sharing', True):
            # Store location tracking preference
            tracking_table = dynamodb.Table('SafeSakhi-LocationTracking')
            tracking_table.put_item(
                Item={
                    'user_id': user_id,
                    'tracking_enabled': True,
                    'emergency_mode': True,
                    'started_at': int(datetime.now().timestamp()),
                    'update_interval': 30  # seconds
                }
            )
            actions.append("Emergency location tracking enabled")
        
        return actions
        
    except Exception as e:
        logger.error(f"Error enabling location tracking: {str(e)}")
        return [f"Location tracking error: {str(e)}"]

def notify_authorities(user_id, risk_assessment):
    """Notify authorities if configured (placeholder for integration)"""
    try:
        # This would integrate with local emergency services APIs
        # For now, log the notification
        logger.info(f"Authority notification for user {user_id}: {risk_assessment}")
        
        # Store notification record
        notification_table = dynamodb.Table('SafeSakhi-AuthorityNotifications')
        notification_table.put_item(
            Item={
                'user_id': user_id,
                'notification_id': f"{user_id}-{int(datetime.now().timestamp())}",
                'timestamp': int(datetime.now().timestamp()),
                'risk_assessment': risk_assessment,
                'status': 'pending',
                'created_at': int(datetime.now().timestamp())
            }
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error notifying authorities: {str(e)}")
        return False

def start_enhanced_monitoring(user_id):
    """Start enhanced monitoring during emergency"""
    try:
        monitoring_id = f"{user_id}-monitoring-{int(datetime.now().timestamp())}"
        
        # Store monitoring configuration
        monitoring_table = dynamodb.Table('SafeSakhi-Monitoring')
        monitoring_table.put_item(
            Item={
                'user_id': user_id,
                'monitoring_id': monitoring_id,
                'monitoring_level': 'emergency',
                'started_at': int(datetime.now().timestamp()),
                'audio_monitoring': True,
                'motion_monitoring': True,
                'location_monitoring': True,
                'update_frequency': 15  # seconds
            }
        )
        
        return monitoring_id
        
    except Exception as e:
        logger.error(f"Error starting enhanced monitoring: {str(e)}")
        return None

def log_emergency_event(user_id, risk_assessment, response_actions, timestamp):
    """Log emergency event for audit and analysis"""
    try:
        events_table = dynamodb.Table('SafeSakhi-EmergencyEvents')
        events_table.put_item(
            Item={
                'user_id': user_id,
                'event_id': f"{user_id}-emergency-{timestamp}",
                'timestamp': timestamp,
                'risk_assessment': risk_assessment,
                'response_actions': response_actions,
                'event_type': 'emergency_response',
                'status': 'active',
                'created_at': int(datetime.now().timestamp())
            }
        )
    except Exception as e:
        logger.error(f"Error logging emergency event: {str(e)}")