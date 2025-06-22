import json
import boto3
import logging
import re
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

comprehend = boto3.client('comprehend')
dynamodb = boto3.resource('dynamodb')

# Threat indicators
COERCION_KEYWORDS = [
    'dont tell anyone', 'keep this secret', 'between us', 'dont go',
    'stay with me', 'you have to', 'you must', 'or else',
    'threat', 'hurt', 'family', 'consequences'
]

CONTROL_PATTERNS = [
    r'where are you',
    r'who are you with',
    r'come back now',
    r'you better',
    r'if you dont',
    r'i know where you live',
    r'watching you'
]

def lambda_handler(event, context):
    try:
        user_id = event['user_id']
        text_data = event['text_data']  # Can be SMS, call transcript, etc.
        message_type = event.get('message_type', 'sms')  # sms, call, chat
        timestamp = event['timestamp']
        sender_info = event.get('sender_info', {})
        
        # Analyze text for threats
        threat_score = analyze_text_threats(text_data, message_type)
        
        # Store analysis results
        store_text_analysis(user_id, timestamp, threat_score, text_data, message_type, sender_info)
        
        # Trigger risk assessment if high threat score
        if threat_score > 0.6:
            trigger_risk_assessment(user_id, 'text', threat_score, {
                'timestamp': timestamp,
                'message_type': message_type,
                'sender_info': sender_info,
                'text_analysis': True
            })
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'threat_score': threat_score,
                'analysis_complete': True,
                'emergency_triggered': threat_score > 0.6
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing text data: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Text processing failed'})
        }

def analyze_text_threats(text, message_type):
    """Analyze text for threat and coercion indicators"""
    try:
        if not text or len(text.strip()) == 0:
            return 0.0
        
        text_lower = text.lower()
        threat_score = 0.0
        
        # Check for coercion keywords
        coercion_matches = sum(1 for keyword in COERCION_KEYWORDS if keyword in text_lower)
        threat_score += min(coercion_matches * 0.2, 0.6)
        
        # Check for control patterns using regex
        control_matches = sum(1 for pattern in CONTROL_PATTERNS if re.search(pattern, text_lower))
        threat_score += min(control_matches * 0.3, 0.7)
        
        # Use Amazon Comprehend for advanced analysis
        comprehend_score = analyze_with_comprehend(text)
        threat_score += comprehend_score * 0.4
        
        # Adjust score based on message type
        if message_type == 'call':
            threat_score *= 1.2  # Calls are more serious
        elif message_type == 'repeated_sms':
            threat_score *= 1.1  # Repeated messages are concerning
        
        return min(threat_score, 1.0)
        
    except Exception as e:
        logger.error(f"Error in text threat analysis: {str(e)}")
        return 0.0

def analyze_with_comprehend(text):
    """Use Amazon Comprehend for advanced text analysis"""
    try:
        # Sentiment analysis
        sentiment_response = comprehend.detect_sentiment(
            Text=text,
            LanguageCode='en'
        )
        
        sentiment_score = 0.0
        if sentiment_response['Sentiment'] == 'NEGATIVE':
            sentiment_score = sentiment_response['SentimentScore']['Negative'] * 0.5
        
        # Key phrase extraction
        keyphrases_response = comprehend.detect_key_phrases(
            Text=text,
            LanguageCode='en'
        )
        
        # Look for threatening key phrases
        threat_phrases = ['physical harm', 'hurt you', 'find you', 'follow you', 'watch you']
        keyphrase_score = 0.0
        
        for phrase in keyphrases_response['KeyPhrases']:
            phrase_text = phrase['Text'].lower()
            if any(threat in phrase_text for threat in threat_phrases):
                keyphrase_score += 0.3
        
        # Entity detection for personal information
        entities_response = comprehend.detect_entities(
            Text=text,
            LanguageCode='en'
        )
        
        # Check if personal info is being referenced (concerning in threats)
        entity_score = 0.0
        personal_entities = ['PERSON', 'LOCATION', 'DATE', 'PHONE_NUMBER']
        
        for entity in entities_response['Entities']:
            if entity['Type'] in personal_entities and entity['Score'] > 0.8:
                entity_score += 0.1
        
        total_score = sentiment_score + min(keyphrase_score, 0.6) + min(entity_score, 0.3)
        return min(total_score, 1.0)
        
    except Exception as e:
        logger.error(f"Comprehend analysis error: {str(e)}")
        return 0.0

def store_text_analysis(user_id, timestamp, threat_score, text_data, message_type, sender_info):
    """Store text analysis results"""
    try:
        table = dynamodb.Table('SafeSakhi-TextAnalysis')
        
        # Store analysis without the actual text content for privacy
        table.put_item(
            Item={
                'user_id': user_id,
                'timestamp': timestamp,
                'threat_score': float(threat_score),
                'message_type': message_type,
                'sender_info': sender_info,
                'text_length': len(text_data),
                'analysis_type': 'text',
                'created_at': timestamp
            }
        )
        
        # If high threat score, store encrypted text for evidence
        if threat_score > 0.7:
            store_evidence_text(user_id, timestamp, text_data, threat_score)
            
    except Exception as e:
        logger.error(f"Error storing text analysis: {str(e)}")

def store_evidence_text(user_id, timestamp, text_data, threat_score):
    """Store high-threat text as encrypted evidence"""
    try:
        # In production, encrypt the text data
        evidence_table = dynamodb.Table('SafeSakhi-Evidence')
        evidence_table.put_item(
            Item={
                'user_id': user_id,
                'evidence_id': f"{user_id}-{timestamp}-text",
                'timestamp': timestamp,
                'evidence_type': 'text',
                'threat_score': float(threat_score),
                'encrypted_content': text_data,  # Should be encrypted in production
                'retention_until': int(datetime.now().timestamp()) + (90 * 24 * 3600),  # 90 days
                'created_at': timestamp
            }
        )
    except Exception as e:
        logger.error(f"Error storing evidence: {str(e)}")

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