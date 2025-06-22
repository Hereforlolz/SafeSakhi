import json
import boto3
import logging
import numpy as np
from scipy import signal
from scipy.stats import entropy

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    try:
        user_id = event['user_id']
        motion_data = event['motion_data']  # Array of accelerometer/gyroscope readings
        timestamp = event['timestamp']
        location = event.get('location', {})
        
        # Analyze motion patterns
        threat_score = analyze_motion_patterns(motion_data)
        
        # Store analysis results
        store_motion_analysis(user_id, timestamp, threat_score, location, motion_data)
        
        # Trigger risk assessment if high threat score
        if threat_score > 0.8:
            trigger_risk_assessment(user_id, 'motion', threat_score, {
                'timestamp': timestamp,
                'location': location,
                'motion_analysis': True
            })
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'threat_score': threat_score,
                'analysis_complete': True,
                'emergency_triggered': threat_score > 0.8
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing motion data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Motion processing failed'})
        }

def analyze_motion_patterns(motion_data):
    """Analyze motion data for threat indicators"""
    try:
        if not motion_data or len(motion_data) < 10:
            return 0.0
        
        # Extract accelerometer and gyroscope data
        accel_x = [d['accel_x'] for d in motion_data]
        accel_y = [d['accel_y'] for d in motion_data]
        accel_z = [d['accel_z'] for d in motion_data]
        gyro_x = [d['gyro_x'] for d in motion_data]
        gyro_y = [d['gyro_y'] for d in motion_data]
        gyro_z = [d['gyro_z'] for d in motion_data]
        
        # Calculate threat indicators
        shake_score = detect_violent_shaking(accel_x, accel_y, accel_z)
        fall_score = detect_fall_pattern(accel_x, accel_y, accel_z)
        struggle_score = detect_struggle_pattern(accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z)
        
        # Combine scores
        combined_score = max(shake_score, fall_score, struggle_score)
        
        return min(combined_score, 1.0)
        
    except Exception as e:
        logger.error(f"Error in motion pattern analysis: {str(e)}")
        return 0.0

def detect_violent_shaking(accel_x, accel_y, accel_z):
    """Detect violent shaking patterns"""
    try:
        # Calculate magnitude of acceleration
        magnitude = np.sqrt(np.array(accel_x)**2 + np.array(accel_y)**2 + np.array(accel_z)**2)
        
        # Remove gravity (assuming phone is held normally)
        magnitude_no_gravity = magnitude - 9.8
        
        # Calculate variance and frequency of high-amplitude movements
        variance = np.var(magnitude_no_gravity)
        high_amplitude_count = np.sum(np.abs(magnitude_no_gravity) > 3.0)  # 3g threshold
        
        # Calculate shake score
        shake_score = min((variance / 10.0) + (high_amplitude_count / len(magnitude) * 2), 1.0)
        
        return shake_score
        
    except Exception as e:
        logger.error(f"Error detecting shaking: {str(e)}")
        return 0.0

def detect_fall_pattern(accel_x, accel_y, accel_z):
    """Detect fall patterns"""
    try:
        magnitude = np.sqrt(np.array(accel_x)**2 + np.array(accel_y)**2 + np.array(accel_z)**2)
        
        # Look for free fall (low acceleration) followed by impact (high acceleration)
        low_accel_threshold = 2.0  # Below normal gravity
        high_accel_threshold = 20.0  # High impact
        
        fall_score = 0.0
        
        for i in range(len(magnitude) - 5):
            window = magnitude[i:i+5]
            if (np.min(window[:3]) < low_accel_threshold and 
                np.max(window[3:]) > high_accel_threshold):
                fall_score = max(fall_score, 0.9)
        
        return fall_score
        
    except Exception as e:
        logger.error(f"Error detecting fall: {str(e)}")
        return 0.0

def detect_struggle_pattern(accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z):
    """Detect struggle/fight patterns"""
    try:
        # Combine accelerometer and gyroscope data
        accel_magnitude = np.sqrt(np.array(accel_x)**2 + np.array(accel_y)**2 + np.array(accel_z)**2)
        gyro_magnitude = np.sqrt(np.array(gyro_x)**2 + np.array(gyro_y)**2 + np.array(gyro_z)**2)
        
        # Calculate entropy (randomness) of motion
        accel_entropy = entropy(np.histogram(accel_magnitude, bins=10)[0] + 1e-10)
        gyro_entropy = entropy(np.histogram(gyro_magnitude, bins=10)[0] + 1e-10)
        
        # High entropy + high magnitude suggests struggle
        combined_entropy = (accel_entropy + gyro_entropy) / 2
        avg_magnitude = np.mean(accel_magnitude)
        
        struggle_score = min((combined_entropy / 3.0) + (avg_magnitude / 20.0), 1.0)
        
        return struggle_score
        
    except Exception as e:
        logger.error(f"Error detecting struggle: {str(e)}")
        return 0.0

def store_motion_analysis(user_id, timestamp, threat_score, location, motion_data):
    """Store motion analysis results"""
    try:
        table = dynamodb.Table('SafeSakhi-MotionAnalysis')
        table.put_item(
            Item={
                'user_id': user_id,
                'timestamp': timestamp,
                'threat_score': float(threat_score),
                'location': location,
                'analysis_type': 'motion',
                'data_points': len(motion_data),
                'created_at': timestamp
            }
        )
    except Exception as e:
        logger.error(f"Error storing motion analysis: {str(e)}")

def trigger_risk_assessment(user_id, trigger_type, score, context):
    """Trigger risk assessment Lambda"""
    try:
        lambda_client = boto3.client('lambda')
        payload = {
            'user_id': user_id,
            'trigger_type': trigger_type,
            'threat_score': score,
            'context': context
        }
        
        lambda_client.invoke(
            FunctionName='SafeSakhi-RiskAssessment',
            InvocationType='Event',
            Payload=json.dumps(payload)
        )
        
    except Exception as e:
        logger.error(f"Error triggering risk assessment: {str(e)}")