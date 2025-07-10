import json
import os
import boto3
import logging
import re
from datetime import datetime
from decimal import Decimal

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

# AWS Clients
dynamodb = boto3.resource('dynamodb')
comprehend = boto3.client('comprehend')
lambda_client = boto3.client('lambda')

# DynamoDB Table Names from Environment Variables
TEXT_ANALYSIS_TABLE_NAME = os.environ.get('TEXT_ANALYSIS_TABLE_NAME')
EVIDENCE_TABLE_NAME = os.environ.get('EVIDENCE_TABLE_NAME')
text_analysis_table = dynamodb.Table(TEXT_ANALYSIS_TABLE_NAME)
evidence_table = dynamodb.Table(EVIDENCE_TABLE_NAME)

# Risk Assessment Lambda Name
RISK_ASSESSMENT_LAMBDA_NAME = os.environ.get('RISK_ASSESSMENT_LAMBDA_NAME')

# Environment Variables for Analysis Thresholds and Keywords
THREAT_SCORE_TRIGGER_THRESHOLD = float(os.environ.get('THREAT_SCORE_TRIGGER_THRESHOLD', '0.6'))
EVIDENCE_STORAGE_THRESHOLD = float(os.environ.get('EVIDENCE_STORAGE_THRESHOLD', '0.7'))
EVIDENCE_RETENTION_DAYS = int(os.environ.get('EVIDENCE_RETENTION_DAYS', '90'))
COMPREHEND_LANGUAGE_CODE = os.environ.get('COMPREHEND_LANGUAGE_CODE', 'en')

# Coercion keywords and control patterns - Handle empty environment variables
COERCION_KEYWORDS_STR = os.environ.get('COERCION_KEYWORDS', '')
COERCION_KEYWORDS = [kw.strip().lower() for kw in COERCION_KEYWORDS_STR.split(',') if kw.strip()]

CONTROL_PATTERNS_STR = os.environ.get('CONTROL_PATTERNS', '')
CONTROL_PATTERNS = []
if CONTROL_PATTERNS_STR:
    try:
        CONTROL_PATTERNS = [re.compile(p.strip(), re.IGNORECASE) for p in CONTROL_PATTERNS_STR.split(',') if p.strip()]
    except re.error as e:
        logger.warning(f"Invalid regex pattern in CONTROL_PATTERNS: {e}")
        CONTROL_PATTERNS = []

# Weights for risk calculation
KEYWORD_COERCION_WEIGHT = float(os.environ.get('KEYWORD_COERCION_WEIGHT', '0.2'))
REGEX_CONTROL_WEIGHT = float(os.environ.get('REGEX_CONTROL_WEIGHT', '0.3'))
COMPREHEND_ANALYSIS_WEIGHT = float(os.environ.get('COMPREHEND_ANALYSIS_WEIGHT', '0.4'))
COMPREHEND_NEGATIVE_SENTIMENT_FACTOR = float(os.environ.get('COMPREHEND_NEGATIVE_SENTIMENT_FACTOR', '0.5'))

COMPREHEND_THREAT_PHRASES_STR = os.environ.get('COMPREHEND_THREAT_PHRASES', '')
COMPREHEND_THREAT_PHRASES = [p.strip().lower() for p in COMPREHEND_THREAT_PHRASES_STR.split(',') if p.strip()]

COMPREHEND_KEYPHRASE_BONUS = float(os.environ.get('COMPREHEND_KEYPHRASE_BONUS', '0.3'))
COMPREHEND_ENTITY_BONUS = float(os.environ.get('COMPREHEND_ENTITY_BONUS', '0.1'))

COMPREHEND_PERSONAL_ENTITY_TYPES_STR = os.environ.get('COMPREHEND_PERSONAL_ENTITY_TYPES', '')
COMPREHEND_PERSONAL_ENTITY_TYPES = [t.strip().upper() for t in COMPREHEND_PERSONAL_ENTITY_TYPES_STR.split(',') if t.strip()]

COMPREHEND_ENTITY_SCORE_THRESHOLD = float(os.environ.get('COMPREHEND_ENTITY_SCORE_THRESHOLD', '0.8'))

# Message type multipliers (parsed from JSON string)
MESSAGE_TYPE_MULTIPLIERS_STR = os.environ.get('MESSAGE_TYPE_MULTIPLIERS', '{}')
try:
    MESSAGE_TYPE_MULTIPLIERS = json.loads(MESSAGE_TYPE_MULTIPLIERS_STR)
except json.JSONDecodeError:
    logger.warning("Invalid JSON in MESSAGE_TYPE_MULTIPLIERS, using empty dict")
    MESSAGE_TYPE_MULTIPLIERS = {}


def convert_to_decimal(value):
    """Convert float/int to Decimal for DynamoDB storage"""
    if value is None:
        return None
    return Decimal(str(value))


def calculate_text_threat_score(text_input, sentiment, key_phrases, entities, message_type):
    """Calculates a threat score based on text analysis."""
    score = 0.0

    # 1. Keyword Coercion Check
    for keyword in COERCION_KEYWORDS:
        if keyword in text_input.lower():
            score += KEYWORD_COERCION_WEIGHT

    # 2. Regex Control Pattern Check
    for pattern in CONTROL_PATTERNS:
        if pattern.search(text_input):
            score += REGEX_CONTROL_WEIGHT

    # 3. Comprehend Analysis
    # Adjust score based on negative sentiment
    if sentiment['Sentiment'] == 'NEGATIVE':
        score += sentiment['SentimentScore']['Negative'] * COMPREHEND_NEGATIVE_SENTIMENT_FACTOR

    # Bonus for specific threat key phrases
    for phrase in COMPREHEND_THREAT_PHRASES:
        if phrase in text_input.lower():
            score += COMPREHEND_KEYPHRASE_BONUS

    # Bonus for personal entities if confidence is high
    for entity in entities:
        if entity['Type'] in COMPREHEND_PERSONAL_ENTITY_TYPES and entity['Score'] >= COMPREHEND_ENTITY_SCORE_THRESHOLD:
            score += COMPREHEND_ENTITY_BONUS

    # Apply overall Comprehend weight
    score *= COMPREHEND_ANALYSIS_WEIGHT

    # Apply message type multiplier
    multiplier = MESSAGE_TYPE_MULTIPLIERS.get(message_type.lower(), 1.0)
    score *= multiplier

    # Ensure score is within 0-1 range
    return min(1.0, max(0.0, score))


def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event, default=str)}")

    try:
        # API Gateway Proxy Integration puts the body as a string under 'body' key
        if 'body' in event and event['body'] is not None:
            body_data = json.loads(event['body'])
        else:
            body_data = event # For direct Lambda invocation or other triggers

        logger.info(f"Parsed body data: {json.dumps(body_data, default=str)}")

        user_id = body_data.get('user_id')
        timestamp = body_data.get('timestamp')
        text_input = body_data.get('text_input')
        message_type = body_data.get('message_type', 'unknown')

        if not all([user_id, timestamp, text_input]):
            logger.error("Validation Error: Missing required fields (user_id, timestamp, text_input).")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required fields (user_id, timestamp, text_input)'})
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

        # Validate text input length (Comprehend has limits)
        if len(text_input) > 5000:
            logger.error(f"Text input too long: {len(text_input)} characters")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Text input too long. Maximum 5000 characters allowed.'})
            }

        # Perform Comprehend analysis with error handling
        try:
            sentiment_response = comprehend.detect_sentiment(
                Text=text_input,
                LanguageCode=COMPREHEND_LANGUAGE_CODE
            )
            logger.info(f"Sentiment analysis completed: {sentiment_response['Sentiment']}")
        except Exception as e:
            logger.error(f"Comprehend sentiment analysis failed: {e}")
            # Use default sentiment if Comprehend fails
            sentiment_response = {
                'Sentiment': 'NEUTRAL',
                'SentimentScore': {
                    'Positive': 0.25,
                    'Negative': 0.25,
                    'Neutral': 0.5,
                    'Mixed': 0.0
                }
            }

        try:
            key_phrases_response = comprehend.detect_key_phrases(
                Text=text_input,
                LanguageCode=COMPREHEND_LANGUAGE_CODE
            )
            key_phrases = key_phrases_response['KeyPhrases']
            logger.info(f"Key phrases detected: {len(key_phrases)}")
        except Exception as e:
            logger.error(f"Comprehend key phrases analysis failed: {e}")
            key_phrases = []

        try:
            entities_response = comprehend.detect_entities(
                Text=text_input,
                LanguageCode=COMPREHEND_LANGUAGE_CODE
            )
            entities = entities_response['Entities']
            logger.info(f"Entities detected: {len(entities)}")
        except Exception as e:
            logger.error(f"Comprehend entities analysis failed: {e}")
            entities = []

        # Calculate threat score
        threat_score = calculate_text_threat_score(
            text_input,
            sentiment_response,
            key_phrases,
            entities,
            message_type
        )

        # Store analysis in DynamoDB - Convert all numeric values to Decimal
        item = {
            'user_id': user_id,
            'timestamp': timestamp,
            'text_input': text_input,
            'message_type': message_type,
            'threat_score': convert_to_decimal(threat_score),
            'sentiment': {
                'Sentiment': sentiment_response['Sentiment'],
                'SentimentScore': {
                    'Positive': convert_to_decimal(sentiment_response['SentimentScore']['Positive']),
                    'Negative': convert_to_decimal(sentiment_response['SentimentScore']['Negative']),
                    'Neutral': convert_to_decimal(sentiment_response['SentimentScore']['Neutral']),
                    'Mixed': convert_to_decimal(sentiment_response['SentimentScore']['Mixed'])
                }
            },
            'key_phrases': [
                {
                    'Text': phrase['Text'],
                    'Score': convert_to_decimal(phrase['Score']),
                    'BeginOffset': phrase['BeginOffset'],
                    'EndOffset': phrase['EndOffset']
                } for phrase in key_phrases
            ],
            'entities': [
                {
                    'Text': entity['Text'],
                    'Type': entity['Type'],
                    'Score': convert_to_decimal(entity['Score']),
                    'BeginOffset': entity['BeginOffset'],
                    'EndOffset': entity['EndOffset']
                } for entity in entities
            ],
            'analysis_time': datetime.utcnow().isoformat()
        }
        
        text_analysis_table.put_item(Item=item)
        logger.info(f"Text analysis stored for user {user_id} at {timestamp} with score {threat_score}")

        # Store evidence if threat score is high enough
        if threat_score >= EVIDENCE_STORAGE_THRESHOLD:
            evidence_id = f"{user_id}-{timestamp}"
            retention_until = int(datetime.now().timestamp()) + (EVIDENCE_RETENTION_DAYS * 24 * 60 * 60)
            evidence_item = {
                'evidence_id': evidence_id,
                'user_id': user_id,
                'timestamp': timestamp,
                'text_input': text_input,
                'threat_score': convert_to_decimal(threat_score),
                'retention_until': retention_until
            }
            evidence_table.put_item(Item=evidence_item)
            logger.info(f"Evidence stored for user {user_id} with ID {evidence_id}")

        # Invoke Risk Assessor Lambda if threat score exceeds threshold
        if threat_score >= THREAT_SCORE_TRIGGER_THRESHOLD:
            logger.info(f"Threat score {threat_score} >= threshold {THREAT_SCORE_TRIGGER_THRESHOLD}. Invoking Risk Assessor.")
            try:
                lambda_client.invoke(
                    FunctionName=RISK_ASSESSMENT_LAMBDA_NAME,
                    InvocationType='Event',
                    Payload=json.dumps({
                        'user_id': user_id,
                        'trigger_type': 'text_analysis',
                        'timestamp': timestamp,
                        'threat_score': float(threat_score)  # Convert back to float for JSON serialization
                    })
                )
                logger.info("Risk Assessor Lambda invoked.")
            except Exception as e:
                logger.error(f"Failed to invoke Risk Assessor Lambda: {e}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Text analysis processed successfully', 
                'threat_score': float(threat_score)
            })
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }