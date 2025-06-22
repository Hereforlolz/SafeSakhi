import json
import boto3
import logging
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    try:
        user_id = event['user_id']
        trigger_type = event['trigger_type']  # audio, motion, text
        trigger_score = event['threat_score']
        trigger_context = event['context']
        
        # Assess overall risk
        risk_assessment = calculate_risk_score(user_id, trigger_type, trigger_score, trigger_context)
        
        # Store risk assessment
        store_risk_assessment(user_id, risk_assessment)
        
        # Trigger emergency response if needed
        if risk_assessment['final_score'] > 0.8:
            trigger_emergency_response(user_id, risk_assessment)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'risk_score': risk_assessment['final_score'],
                'risk_level': risk_assessment['risk_level'],
                'emergency_triggered': risk_assessment['final_score'] > 0.8
            })
        }
        
    except Exception as e:
        logger.error(f"Error in risk assessment: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Risk assessment failed'})
        }

def calculate_risk_score(user_id, trigger_type, trigger_score, trigger_context):
    """Calculate comprehensive risk score"""
    try:
        current_time = int(datetime.now().timestamp())
        
        # Get user's risk profile
        user_profile = get_user_risk_profile(user_id)
        
        # Get recent threat indicators (last 30 minutes)
        recent_threats = get_recent_threats(user_id, current_time - 1800)
        
        # Base score from current trigger
        base_score = trigger_score
        
        # Escalation based on recent activity
        escalation_score = calculate_escalation_score(recent_threats, trigger_type)
        
        # Context-based adjustments
        context_score = calculate_context_score(trigger_context, user_profile)
        
        # Historical pattern analysis
        pattern_score = analyze_historical_patterns(user_id, trigger_type)
        
        # Combine scores with weights
        final_score = (
            base_score * 0.4 +
            escalation_score * 0.3 +
            context_score * 0.2 +
            pattern_score * 0.1
        )
        
        # Determine risk level
        if final_score >= 0.9:
            risk_level = 'CRITICAL'
        elif final_score >= 0.7:
            risk_level = 'HIGH'
        elif final_score >= 0.5:
            risk_level = 'MEDIUM'
        elif final_score >= 0.3:
            risk_level = 'LOW'
        else:
            risk_level = 'MINIMAL'
        
        return {
            'final_score': final_score,
            'risk_level': risk_level,
            'base_score': base_score,
            'escalation_score': escalation_score,
            'context_score': context_score,
            'pattern_score': pattern_score,
            'trigger_type': trigger_type,
            'timestamp': current_time,
            'recent_threats_count': len(recent_threats)
        }
        
    except Exception as e:
        logger.error(f"Error calculating risk score: {str(e)}")
        return {
            'final_score': trigger_score,
            'risk_level': 'UNKNOWN',
            'error': str(e)
        }

def get_user_risk_profile(user_id):
    """Get user's risk profile and preferences"""
    try:
        table = dynamodb.Table('SafeSakhi-Users')
        response = table.get_item(Key={'user_id': user_id})
        
        if 'Item' in response:
            return response['Item']
        else:
            # Return default profile
            return {
                'user_id': user_id,
                'risk_tolerance': 0.5,
                'location_tracking': True,
                'emergency_contacts': [],
                'high_risk_areas': [],
                'created_at': int(datetime.now().timestamp())
            }
            
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        return {'user_id': user_id, 'risk_tolerance': 0.5}

def get_recent_threats(user_id, since_timestamp):
    """Get recent threat indicators for escalation analysis"""
    try:
        recent_threats = []
        
        # Check audio analysis
        audio_table = dynamodb.Table('SafeSakhi-AudioAnalysis')
        audio_response = audio_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id),
            FilterExpression=boto3.dynamodb.conditions.Attr('timestamp').gte(since_timestamp)
        )
        recent_threats.extend(audio_response['Items'])
        
        # Check motion analysis
        motion_table = dynamodb.Table('SafeSakhi-MotionAnalysis')
        motion_response = motion_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id),
            FilterExpression=boto3.dynamodb.conditions.Attr('timestamp').gte(since_timestamp)
        )
        recent_threats.extend(motion_response['Items'])
        
        # Check text analysis
        text_table = dynamodb.Table('SafeSakhi-TextAnalysis')
        text_response = text_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id),
            FilterExpression=boto3.dynamodb.conditions.Attr('timestamp').gte(since_timestamp)
        )
        recent_threats.extend(text_response['Items'])
        
        return recent_threats
        
    except Exception as e:
        logger.error(f"Error getting recent threats: {str(e)}")
        return []

def calculate_escalation_score(recent_threats, current_trigger_type):
    """Calculate escalation score based on recent activity"""
    if not recent_threats:
        return 0.0
    
    # Count threats by type
    threat_counts = {'audio': 0, 'motion': 0, 'text': 0}
    high_threat_count = 0
    
    for threat in recent_threats:
        threat_type = threat.get('analysis_type', 'unknown')
        threat_score = float(threat.get('threat_score', 0))
        
        if threat_type in threat_counts:
            threat_counts[threat_type] += 1
        
        if threat_score > 0.6:
            high_threat_count += 1
    
    # Multiple threat types indicate escalation
    active_threat_types = sum(1 for count in threat_counts.values() if count > 0)
    
    # Calculate escalation score
    escalation_score = 0.0
    
    # Multiple threat types
    if active_threat_types >= 2:
        escalation_score += 0.4
    
    # High number of threats
    if len(recent_threats) > 3:
        escalation_score += 0.3
    
    # High severity threats
    if high_threat_count > 1:
        escalation_score += 0.3
    
    return min(escalation_score, 1.0)

def calculate_context_score(trigger_context, user_profile):
    """Calculate context-based risk adjustments"""
    context_score = 0.0
    
    # Time-based risk (late night/early morning)
    current_hour = datetime.now().hour
    if current_hour >= 22 or current_hour <= 5:
        context_score += 0.2
    
    # Location-based risk
    location = trigger_context.get('location', {})
    if location:
        # Check if in high-risk area
        high_risk_areas = user_profile.get('high_risk_areas', [])
        current_lat = location.get('latitude')
        current_lon = location.get('longitude')
        
        if current_lat and current_lon:
            for risk_area in high_risk_areas:
                # Simple distance check (in production, use proper geospatial queries)
                if (abs(current_lat - risk_area.get('lat', 0)) < 0.01 and 
                    abs(current_lon - risk_area.get('lon', 0)) < 0.01):
                    context_score += 0.3
                    break
    
    # Isolated location (no recent movement)
    if not location or location.get('accuracy', 0) > 100:
        context_score += 0.1
    
    return min(context_score, 1.0)

def analyze_historical_patterns(user_id, trigger_type):
    """Analyze historical patterns for false positive reduction"""
    try:
        # Get historical data (last 7 days)
        week_ago = int((datetime.now() - timedelta(days=7)).timestamp())
        
        # This would involve more complex analysis in production
        # For now, return a simple baseline
        return 0.1
        
    except Exception as e:
        logger.error(f"Error in pattern analysis: {str(e)}")
        return 0.0

def store_risk_assessment(user_id, risk_assessment):
    """Store risk assessment results"""
    try:
        table = dynamodb.Table('SafeSakhi-RiskAssessments')
        table.put_item(
            Item={
                'user_id': user_id,
                'timestamp': risk_assessment['timestamp'],
                'final_score': Decimal(str(risk_assessment['final_score'])),
                'risk_level': risk_assessment['risk_level'],
                'base_score': Decimal(str(risk_assessment['base_score'])),
                'escalation_score': Decimal(str(risk_assessment['escalation_score'])),
                'context_score': Decimal(str(risk_assessment['context_score'])),
                'pattern_score': Decimal(str(risk_assessment['pattern_score'])),
                'trigger_type': risk_assessment['trigger_type'],
                'recent_threats_count': risk_assessment['recent_threats_count']
            }
        )
    except Exception as e:
        logger.error(f"Error storing risk assessment: {str(e)}")

def trigger_emergency_response(user_id, risk_assessment):
    """Trigger emergency response Lambda"""
    try:
        payload = {
            'user_id': user_id,
            'risk_assessment': risk_assessment,
            'emergency_type': 'high_risk_detected',
            'timestamp': risk_assessment['timestamp']
        }
        
        lambda_client.invoke(
            FunctionName='SafeSakhi-EmergencyResponse',
            InvocationType='Event',
            Payload=json.dumps(payload, default=str)
        )
        
    except Exception as e:
        logger.error(f"Error triggering emergency response: {str(e)}")