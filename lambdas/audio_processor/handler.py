import json
import boto3
import logging
import base64
import numpy as np
from scipy import signal
import librosa

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
transcribe = boto3.client('transcribe')
comprehend = boto3.client('comprehend')
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

# Threat keywords and patterns
THREAT_KEYWORDS = [
    'help', 'stop', 'no', 'dont', 'leave me alone', 'get away',
    'call police', 'emergency', 'danger', 'scared', 'hurt'
]

DISTRESS_PATTERNS = [
    'please stop', 'I said no', 'help me', 'somebody help',
    'call 911', 'get off me', 'leave me alone'
]

def lambda_handler(event, context):
    try:
        user_id = event['user_id']
        audio_data = event['audio_data']  # Base64 encoded
        timestamp = event['timestamp']
        location = event.get('location', {})
        
        # Decode audio data
        audio_bytes = base64.b64decode(audio_data)
        
        # Analyze audio for threats
        threat_score = analyze_audio_threats(audio_bytes, user_id, timestamp)
        
        # Store analysis results
        store_audio_analysis(user_id, timestamp, threat_score, location)
        
        # Trigger risk assessment if high threat score
        if threat_score > 0.7:
            trigger_risk_assessment(user_id, 'audio', threat_score, {
                'timestamp': timestamp,
                'location': location,
                'audio_analysis': True
            })
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'threat_score': threat_score,
                'analysis_complete': True,
                'emergency_triggered': threat_score > 0.7
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Audio processing failed'})
        }

def analyze_audio_threats(audio_bytes, user_id, timestamp):
    """Analyze audio for threat indicators"""
    try:
        # Convert audio to text using Amazon Transcribe
        transcription = transcribe_audio(audio_bytes, user_id, timestamp)
        
        if not transcription:
            return 0.0
        
        # Analyze text for threats
        text_threat_score = analyze_text_threats(transcription)
        
        # Analyze audio features (volume, pitch, etc.)
        audio_threat_score = analyze_audio_features(audio_bytes)
        
        # Combine scores
        combined_score = (text_threat_score * 0.7) + (audio_threat_score * 0.3)
        
        return min(combined_score, 1.0)
        
    except Exception as e:
        logger.error(f"Error in threat analysis: {str(e)}")
        return 0.0

def transcribe_audio(audio_bytes, user_id, timestamp):
    """Transcribe audio using Amazon Transcribe"""
    try:
        # Upload audio to S3 for Transcribe
        bucket_name = 'safesakhi-audio-temp'
        key = f"audio/{user_id}/{timestamp}.wav"
        
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=audio_bytes,
            ContentType='audio/wav'
        )
        
        # Start transcription job
        job_name = f"audio-analysis-{user_id}-{timestamp}"
        job_uri = f"s3://{bucket_name}/{key}"
        
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': job_uri},
            MediaFormat='wav',
            LanguageCode='en-US'
        )
        
        # Wait for completion (in production, use async processing)
        import time
        while True:
            status = transcribe.get_transcription_job(
                TranscriptionJobName=job_name
            )
            if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
                break
            time.sleep(2)
        
        if status['TranscriptionJob']['TranscriptionJobStatus'] == 'COMPLETED':
            # Get transcript
            transcript_uri = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
            import urllib.request
            with urllib.request.urlopen(transcript_uri) as response:
                transcript_data = json.loads(response.read().decode())
                return transcript_data['results']['transcripts'][0]['transcript']
        
        return None
        
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        return None

def analyze_text_threats(text):
    """Analyze transcribed text for threat indicators"""
    if not text:
        return 0.0
    
    text_lower = text.lower()
    threat_score = 0.0
    
    # Check for direct threat keywords
    keyword_matches = sum(1 for keyword in THREAT_KEYWORDS if keyword in text_lower)
    threat_score += min(keyword_matches * 0.3, 0.6)
    
    # Check for distress patterns
    pattern_matches = sum(1 for pattern in DISTRESS_PATTERNS if pattern in text_lower)
    threat_score += min(pattern_matches * 0.4, 0.8)
    
    # Use Amazon Comprehend for sentiment analysis
    try:
        sentiment_response = comprehend.detect_sentiment(
            Text=text,
            LanguageCode='en'
        )
        
        if sentiment_response['Sentiment'] == 'NEGATIVE':
            negative_score = sentiment_response['SentimentScore']['Negative']
            threat_score += negative_score * 0.3
            
    except Exception as e:
        logger.error(f"Sentiment analysis error: {str(e)}")
    
    return min(threat_score, 1.0)

def analyze_audio_features(audio_bytes):
    """Analyze raw audio features for distress indicators"""
    try:
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # Normalize audio
        audio_normalized = audio_array.astype(np.float32) / 32768.0
        
        # Calculate features
        rms_energy = np.sqrt(np.mean(audio_normalized**2))
        zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(audio_normalized))
        
        # High energy + high ZCR often indicates shouting/distress
        energy_score = min(rms_energy * 2, 1.0)  # Normalize to 0-1
        zcr_score = min(zero_crossing_rate * 10, 1.0)  # Normalize to 0-1
        
        # Combine features
        audio_threat_score = (energy_score * 0.6) + (zcr_score * 0.4)
        
        return audio_threat_score
        
    except Exception as e:
        logger.error(f"Audio feature analysis error: {str(e)}")
        return 0.0

def store_audio_analysis(user_id, timestamp, threat_score, location):
    """Store analysis results in DynamoDB"""
    try:
        table = dynamodb.Table('SafeSakhi-AudioAnalysis')
        table.put_item(
            Item={
                'user_id': user_id,
                'timestamp': timestamp,
                'threat_score': float(threat_score),
                'location': location,
                'analysis_type': 'audio',
                'created_at': timestamp
            }
        )
    except Exception as e:
        logger.error(f"Error storing audio analysis: {str(e)}")

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
            InvocationType='Event',  # Async invocation
            Payload=json.dumps(payload)
        )
        
    except Exception as e:
        logger.error(f"Error triggering risk assessment: {str(e)}")