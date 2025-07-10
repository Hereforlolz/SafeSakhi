import json
import boto3
import logging
import googlemaps
import requests
from datetime import datetime, timedelta
from urllib.parse import quote

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
s3 = boto3.client('s3')

# Initialize Google Maps client
gmaps = googlemaps.Client(key='YOUR_GOOGLE_MAPS_API_KEY')

def lambda_handler(event, context):
    try:
        user_id = event['user_id']
        risk_assessment = event['risk_assessment']
        emergency_type = event['emergency_type']
        timestamp = event['timestamp']
        
        # Get user's emergency preferences and location
        user_profile = get_user_profile(user_id)
        emergency_contacts = user_profile.get('emergency_contacts', [])
        preferences = user_profile.get('emergency_preferences', {})
        current_location = event.get('location', user_profile.get('last_known_location'))
        
        # Get location intelligence for emergency response
        location_context = get_emergency_location_context(current_location)
        
        # Execute enhanced emergency response with location data
        response_actions = execute_emergency_response(
            user_id, risk_assessment, emergency_contacts, preferences, 
            current_location, location_context
        )
        
        # Log emergency event with location context
        log_emergency_event(user_id, risk_assessment, response_actions, timestamp, location_context)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'emergency_response_initiated': True,
                'actions_taken': response_actions,
                'location_context': location_context,
                'timestamp': timestamp
            })
        }
        
    except Exception as e:
        logger.error(f"Error in emergency response: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Emergency response failed'})
        }

def get_emergency_location_context(location):
    """Get comprehensive location context for emergency response"""
    if not location or not location.get('lat') or not location.get('lng'):
        return None
    
    try:
        lat, lng = location['lat'], location['lng']
        
        context = {
            'current_address': None,
            'nearest_emergency_services': {},
            'safe_zones': [],
            'evacuation_routes': [],
            'area_characteristics': {},
            'emergency_resources': []
        }
        
        # Get current address
        try:
            reverse_result = gmaps.reverse_geocode((lat, lng))
            if reverse_result:
                context['current_address'] = reverse_result[0]['formatted_address']
                context['area_characteristics'] = analyze_area_characteristics(reverse_result[0])
        except Exception as e:
            logger.error(f"Reverse geocoding error: {str(e)}")
        
        # Find nearest emergency services
        context['nearest_emergency_services'] = find_nearest_emergency_services(lat, lng)
        
        # Identify safe zones
        context['safe_zones'] = identify_safe_zones(lat, lng)
        
        # Generate evacuation routes
        context['evacuation_routes'] = generate_evacuation_routes(lat, lng, context['safe_zones'])
        
        # Get comprehensive emergency resources
        context['emergency_resources'] = get_emergency_resources(lat, lng)
        
        return context
        
    except Exception as e:
        logger.error(f"Error getting location context: {str(e)}")
        return None

def find_nearest_emergency_services(lat, lng, radius=5000):
    """Find nearest emergency services with detailed information"""
    try:
        emergency_services = {
            'police': [],
            'hospitals': [],
            'fire_stations': [],
            'ambulance_services': []
        }
        
        # Search for police stations
        police_results = gmaps.places_nearby(
            location=(lat, lng),
            radius=radius,
            type='police'
        )
        
        for place in police_results.get('results', [])[:5]:
            service_info = {
                'name': place.get('name'),
                'place_id': place.get('place_id'),
                'location': place['geometry']['location'],
                'distance': calculate_distance(lat, lng, 
                    place['geometry']['location']['lat'],
                    place['geometry']['location']['lng']),
                'rating': place.get('rating'),
                'phone': get_place_phone(place.get('place_id')),
                'open_now': place.get('opening_hours', {}).get('open_now'),
                'directions_url': generate_directions_url(lat, lng, place['geometry']['location'])
            }
            emergency_services['police'].append(service_info)
        
        # Search for hospitals
        hospital_results = gmaps.places_nearby(
            location=(lat, lng),
            radius=radius,
            type='hospital'
        )
        
        for place in hospital_results.get('results', [])[:5]:
            service_info = {
                'name': place.get('name'),
                'place_id': place.get('place_id'),
                'location': place['geometry']['location'],
                'distance': calculate_distance(lat, lng, 
                    place['geometry']['location']['lat'],
                    place['geometry']['location']['lng']),
                'rating': place.get('rating'),
                'phone': get_place_phone(place.get('place_id')),
                'open_now': place.get('opening_hours', {}).get('open_now'),
                'directions_url': generate_directions_url(lat, lng, place['geometry']['location']),
                'emergency_services': True  # Hospitals typically have 24/7 emergency
            }
            emergency_services['hospitals'].append(service_info)
        
        # Search for fire stations
        fire_results = gmaps.places_nearby(
            location=(lat, lng),
            radius=radius,
            type='fire_station'
        )
        
        for place in fire_results.get('results', [])[:3]:
            service_info = {
                'name': place.get('name'),
                'place_id': place.get('place_id'),
                'location': place['geometry']['location'],
                'distance': calculate_distance(lat, lng, 
                    place['geometry']['location']['lat'],
                    place['geometry']['location']['lng']),
                'phone': get_place_phone(place.get('place_id')),
                'directions_url': generate_directions_url(lat, lng, place['geometry']['location'])
            }
            emergency_services['fire_stations'].append(service_info)
        
        # Sort all services by distance
        for service_type in emergency_services:
            emergency_services[service_type].sort(key=lambda x: x['distance'])
        
        return emergency_services
        
    except Exception as e:
        logger.error(f"Error finding emergency services: {str(e)}")
        return {}

def identify_safe_zones(lat, lng, radius=3000):
    """Identify safe zones near the current location"""
    try:
        safe_zones = []
        
        # Types of places that are generally considered safe
        safe_place_types = [
            'shopping_mall',
            'library',
            'school',
            'university',
            'government_office',
            'embassy',
            'church',
            'mosque',
            'synagogue',
            'hospital',
            'police'
        ]
        
        for place_type in safe_place_types:
            try:
                places_result = gmaps.places_nearby(
                    location=(lat, lng),
                    radius=radius,
                    type=place_type
                )
                
                for place in places_result.get('results', [])[:3]:
                    safe_zone = {
                        'name': place.get('name'),
                        'type': place_type,
                        'location': place['geometry']['location'],
                        'distance': calculate_distance(lat, lng, 
                            place['geometry']['location']['lat'],
                            place['geometry']['location']['lng']),
                        'rating': place.get('rating'),
                        'open_now': place.get('opening_hours', {}).get('open_now'),
                        'directions_url': generate_directions_url(lat, lng, place['geometry']['location']),
                        'safety_score': calculate_safety_score(place_type, place.get('rating', 0))
                    }
                    safe_zones.append(safe_zone)
                    
            except Exception as e:
                logger.error(f"Error finding {place_type}: {str(e)}")
                continue
        
        # Sort by safety score and distance
        safe_zones.sort(key=lambda x: (x['safety_score'], -x['distance']), reverse=True)
        return safe_zones[:10]  # Return top 10 safe zones
        
    except Exception as e:
        logger.error(f"Error identifying safe zones: {str(e)}")
        return []

def generate_evacuation_routes(lat, lng, safe_zones):
    """Generate evacuation routes to safe zones"""
    try:
        evacuation_routes = []
        
        for safe_zone in safe_zones[:5]:  # Top 5 safe zones
            try:
                # Get directions to safe zone
                directions_result = gmaps.directions(
                    origin=(lat, lng),
                    destination=(safe_zone['location']['lat'], safe_zone['location']['lng']),
                    mode="walking",
                    alternatives=True
                )
                
                if directions_result:
                    for i, route in enumerate(directions_result[:2]):  # Max 2 routes per destination
                        evacuation_route = {
                            'destination': safe_zone['name'],
                            'destination_type': safe_zone['type'],
                            'route_number': i + 1,
                            'distance': route['legs'][0]['distance']['text'],
                            'duration': route['legs'][0]['duration']['text'],
                            'steps': [],
                            'polyline': route['overview_polyline']['points'],
                            'warnings': route.get('warnings', [])
                        }
                        
                        # Extract key steps
                        for step in route['legs'][0]['steps'][:5]:  # First 5 steps
                            evacuation_route['steps'].append({
                                'instruction': step['html_instructions'],
                                'distance': step['distance']['text'],
                                'duration': step['duration']['text']
                            })
                        
                        evacuation_routes.append(evacuation_route)
                        
            except Exception as e:
                logger.error(f"Error generating route to {safe_zone['name']}: {str(e)}")
                continue
        
        return evacuation_routes
        
    except Exception as e:
        logger.error(f"Error generating evacuation routes: {str(e)}")
        return []

def get_emergency_resources(lat, lng):
    """Get comprehensive emergency resources"""
    try:
        resources = []
        
        # Search for various emergency-related places
        resource_types = [
            ('pharmacy', 'Medical supplies'),
            ('gas_station', 'Fuel and supplies'),
            ('atm', 'Emergency cash'),
            ('taxi_stand', 'Transportation'),
            ('bus_station', 'Public transport'),
            ('subway_station', 'Public transport'),
            ('hotel', 'Temporary shelter'),
            ('restaurant', 'Food and shelter')
        ]
        
        for place_type, description in resource_types:
            try:
                places_result = gmaps.places_nearby(
                    location=(lat, lng),
                    radius=2000,
                    type=place_type
                )
                
                for place in places_result.get('results', [])[:2]:
                    resource = {
                        'name': place.get('name'),
                        'type': place_type,
                        'description': description,
                        'location': place['geometry']['location'],
                        'distance': calculate_distance(lat, lng, 
                            place['geometry']['location']['lat'],
                            place['geometry']['location']['lng']),
                        'rating': place.get('rating'),
                        'open_now': place.get('opening_hours', {}).get('open_now'),
                        'directions_url': generate_directions_url(lat, lng, place['geometry']['location'])
                    }
                    resources.append(resource)
                    
            except Exception as e:
                logger.error(f"Error finding {place_type}: {str(e)}")
                continue
        
        # Sort by distance
        resources.sort(key=lambda x: x['distance'])
        return resources[:15]  # Return top 15 resources
        
    except Exception as e:
        logger.error(f"Error getting emergency resources: {str(e)}")
        return []

def calculate_safety_score(place_type, rating):
    """Calculate safety score for different place types"""
    type_scores = {
        'police': 1.0,
        'hospital': 0.95,
        'government_office': 0.9,
        'embassy': 0.9,
        'shopping_mall': 0.8,
        'library': 0.75,
        'school': 0.7,
        'university': 0.7,
        'church': 0.65,
        'mosque': 0.65,
        'synagogue': 0.65
    }
    
    base_score = type_scores.get(place_type, 0.5)
    rating_bonus = (rating / 5.0) * 0.2 if rating else 0
    
    return min(base_score + rating_bonus, 1.0)

def analyze_area_characteristics(geocode_result):
    """Analyze area characteristics for emergency planning"""
    try:
        characteristics = {
            'area_type': 'unknown',
            'population_density': 'unknown',
            'safety_level': 'unknown'
        }
        
        address_components = geocode_result.get('address_components', [])
        
        # Determine area type
        for component in address_components:
            types = component.get('types', [])
            if 'locality' in types:
                characteristics['area_type'] = 'urban'
                characteristics['population_density'] = 'high'
            elif 'sublocality' in types:
                characteristics['area_type'] = 'suburban'
                characteristics['population_density'] = 'medium'
            elif 'administrative_area_level_3' in types:
                characteristics['area_type'] = 'rural'
                characteristics['population_density'] = 'low'
        
        return characteristics
        
    except Exception as e:
        logger.error(f"Error analyzing area characteristics: {str(e)}")
        return {}

def get_place_phone(place_id):
    """Get phone number for a place"""
    if not place_id:
        return None
    
    try:
        place_details = gmaps.place(place_id=place_id, fields=['formatted_phone_number'])
        return place_details.get('result', {}).get('formatted_phone_number')
    except Exception as e:
        logger.error(f"Error getting place phone: {str(e)}")
        return None

def generate_directions_url(origin_lat, origin_lng, destination):
    """Generate Google Maps directions URL"""
    try:
        dest_lat = destination['lat']
        dest_lng = destination['lng']
        
        return f"https://www.google.com/maps/dir/{origin_lat},{origin_lng}/{dest_lat},{dest_lng}"
        
    except Exception as e:
        logger.error(f"Error generating directions URL: {str(e)}")
        return None

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points using Haversine formula"""
    import math
    
    R = 6371  # Earth's radius in km
    
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    
    a = (math.sin(dlat/2) * math.sin(dlat/2) + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlng/2) * math.sin(dlng/2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    
    return distance * 1000  # Convert to meters

def get_user_profile(user_id):
    """Get user profile with emergency contacts"""
    try:
        table = dynamodb.Table('SafeSakhi-Users')
        response = table.get_item(Key={'user_id': user_id})
        return response.get('Item', {})
    except Exception as e:
        logger.error(f"Error getting user profile: {str(e)}")
        return {}

def execute_emergency_response(user_id, risk_assessment, emergency_contacts, preferences, current_location, location_context):
    """Execute enhanced emergency response actions with location intelligence"""
    actions_taken = []
    
    try:
        # 1. Send location-aware alerts to emergency contacts
        if emergency_contacts:
            sent_alerts = send_location_aware_alerts(
                user_id, risk_assessment, emergency_contacts, current_location, location_context
            )
            actions_taken.extend(sent_alerts)
        
        # 2. Start evidence collection with location data
        evidence_id = start_evidence_collection(user_id, risk_assessment, location_context)
        if evidence_id:
            actions_taken.append(f"Evidence collection started: {evidence_id}")
        
        # 3. Enable enhanced location tracking
        location_updates = enable_enhanced_location_tracking(user_id, preferences, location_context)
        actions_taken.extend(location_updates)
        
        # 4. Create emergency action plan
        action_plan = create_emergency_action_plan(current_location, location_context)
        if action_plan:
            actions_taken.append("Emergency action plan created")
        
        # 5. Notify authorities with location data
        if preferences.get('auto_notify_authorities', False):
            authority_notification = notify_authorities_with_location(
                user_id, risk_assessment, current_location, location_context
            )
            if authority_notification:
                actions_taken.append("Authorities notified with location data")
        
        # 6. Start continuous monitoring with location awareness
        monitoring_id = start_location_aware_monitoring(user_id, current_location)
        if monitoring_id:
            actions_taken.append(f"Location-aware monitoring started: {monitoring_id}")
        
        return actions_taken
        
    except Exception as e:
        logger.error(f"Error executing emergency response: {str(e)}")
        return [f"Error: {str(e)}"]

def send_location_aware_alerts(user_id, risk_assessment, emergency_contacts, current_location, location_context):
    """Send alerts with comprehensive location information"""
    sent_alerts = []
    
    try:
        for contact in emergency_contacts:
            contact_method = contact.get('method', 'sms')
            contact_value = contact.get('value')
            contact_name = contact.get('name', 'Contact')
            
            if not contact_value:
                continue
            
            # Create detailed alert message with location
            alert_message = create_location_aware_alert_message(
                user_id, risk_assessment, contact_name, current_location, location_context
            )
            
            if contact_method == 'sms':
                response = sns.publish(
                    PhoneNumber=contact_value,
                    Message=alert_message,
                    Subject='SafeSakhi Emergency Alert'
                )
                sent_alerts.append(f"Location-aware SMS sent to {contact_name}")
                
            elif contact_method == 'email':
                topic_arn = f"arn:aws:sns:us-east-1:123456789012:SafeSakhi-EmergencyAlerts"
                response = sns.publish(
                    TopicArn=topic_arn,
                    Message=alert_message,
                    Subject='SafeSakhi Emergency Alert - Location Included',
                    MessageAttributes={
                        'email': {
                            'DataType': 'String',
                            'StringValue': contact_value
                        }
                    }
                )
                sent_alerts.append(f"Location-aware email sent to {contact_name}")
        
        return sent_alerts
        
    except Exception as e:
        logger.error(f"Error sending location-aware alerts: {str(e)}")
        return [f"Alert error: {str(e)}"]

def create_location_aware_alert_message(user_id, risk_assessment, contact_name, current_location, location_context):
    """Create comprehensive emergency alert message with location data"""
    risk_level = risk_assessment.get('risk_level', 'HIGH')
    timestamp = datetime.fromtimestamp(risk_assessment.get('timestamp', 0))
    
    message = f"""🚨 SAFESAKHI EMERGENCY ALERT 🚨

Risk Level: {risk_level}
Time: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
User ID: {user_id}

📍 LOCATION INFORMATION:
"""
    
    if current_location and current_location.get('lat') and current_location.get('lng'):
        message += f"Coordinates: {current_location['lat']}, {current_location['lng']}\n"
        message += f"Google Maps: https://maps.google.com/?q={current_location['lat']},{current_location['lng']}\n"
    
    if location_context:
        if location_context.get('current_address'):
            message += f"Address: {location_context['current_address']}\n"
        
        # Add nearest emergency services
        if location_context.get('nearest_emergency_services'):
            services = location_context['nearest_emergency_services']
            message += "\n🚑 NEAREST EMERGENCY SERVICES:\n"
            
            if services.get('police'):
                police = services['police'][0]
                message += f"Police: {police['name']} ({police['distance']:.0f}m)\n"
            
            if services.get('hospitals'):
                hospital = services['hospitals'][0]
                message += f"Hospital: {hospital['name']} ({hospital['distance']:.0f}m)\n"
        
        # Add safe zones
        if location_context.get('safe_zones'):
            message += "\n🏢 NEAREST SAFE ZONES:\n"
            for safe_zone in location_context['safe_zones'][:3]:
                message += f"• {safe_zone['name']} ({safe_zone['distance']:.0f}m)\n"
    
    message += f"""
⚠️ EMERGENCY ACTIONS:
1. Try to contact the user immediately
2. If no response, consider calling local emergency services
3. Check SafeSakhi app for real-time updates
4. Use the location information above to guide help

This alert was generated by AI analysis of potential threat indicators.
Reply STOP to unsubscribe.
"""
    
    return message.strip()

def create_emergency_action_plan(current_location, location_context):
    """Create an emergency action plan based on location"""
    if not location_context:
        return None
    
    try:
        action_plan = {
            'immediate_actions': [],
            'safe_zones': location_context.get('safe_zones', [])[:5],
            'evacuation_routes': location_context.get('evacuation_routes', [])[:3],
            'emergency_contacts': location_context.get('nearest_emergency_services', {}),
            'resources': location_context.get('emergency_resources', [])[:10]
        }
        
        # Store action plan
        table = dynamodb.Table('SafeSakhi-EmergencyActionPlans')
        table.put_item(
            Item={
                'user_id': current_location.get('user_id') if current_location else 'unknown',
                'plan_id': f"plan-{int(datetime.now().timestamp())}",
                'created_at': int(datetime.now().timestamp()),
                'current_location': current_location,
                'action_plan': action_plan,
                'status': 'active'
            }
        )
        
        return action_plan
        
    except Exception as e:
        logger.error(f"Error creating action plan: {str(e)}")
        return None

def notify_authorities_with_location(user_id, risk_assessment, current_location, location_context):
    """Notify authorities with comprehensive location data"""
    try:
        authority_data = {
            'user_id': user_id,
            'risk_assessment': risk_assessment,
            'location': current_location,
            'location_context': location_context,
            'timestamp': int(datetime.now().timestamp())
        }
        
        # Store authority notification with location data
        table = dynamodb.Table('SafeSakhi-AuthorityNotifications')
        table.put_item(
            Item={
                'user_id': user_id,
                'notification_id': f"{user_id}-{int(datetime.now().timestamp())}",
                'timestamp': int(datetime.now().timestamp()),
                'authority_data': authority_data,
                'status': 'pending_with_location',
                'priority': 'high'
            }
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Error notifying authorities: {str(e)}")
        return False

# Keep existing functions with minimal changes
def start_evidence_collection(user_id, risk_assessment, location_context):
    """Start collecting evidence with location context"""
    try:
        evidence_id = f"{user_id}-{int(datetime.now().timestamp())}-emergency"
        
        evidence_table = dynamodb.Table('SafeSakhi-Evidence')
        evidence_table.put_item(
            Item={
                'user_id': user_id,
                'evidence_id': evidence_id,
                'timestamp': risk_assessment.get('timestamp'),
                'evidence_type': 'emergency_context',
                'risk_assessment': risk_assessment,
                'location_context': location_context,
                'collection_active': True,
                'created_at': int(datetime.now().timestamp())
            }
        )
        
        return evidence_id
        
    except Exception as e:
        logger.error(f"Error starting evidence collection: {str(e)}")
        return None

def enable_enhanced_location_tracking(user_id, preferences, location_context):
    """Enable enhanced location tracking with context"""
    actions = []
    
    try:
        if preferences.get('emergency_location_sharing', True):
            tracking_table = dynamodb.Table('SafeSakhi-LocationTracking')
            tracking_table.put_item(
                Item={
                    'user_id': user_id,
                    'tracking_enabled': True,
                    'emergency_mode': True,
                    'location_context': location_context,
                    'started_at': int(datetime.now().timestamp()),
                    'update_interval': 30,  # seconds
                    'high_accuracy': True
                }
            )
            actions.append("Enhanced location tracking with context enabled")
        
        return actions
        
    except Exception as e:
        logger.error(f"Error enabling location tracking: {str(e)}")
        return [f"Location tracking error: {str(e)}"]

def start_location_aware_monitoring(user_id, current_location):
    """Start monitoring with location awareness"""
    try:
        monitoring_id = f"{user_id}-monitoring-{int(datetime.now().timestamp())}"
        
        monitoring_table = dynamodb.Table('SafeSakhi-Monitoring')
        monitoring_table.put_item(
            Item={
                'user_id': user_id,
                'monitoring_id': monitoring_id,
                'monitoring_level': 'emergency',
                'location_aware': True,
                'current_location': current_location,
                'started_at': int(datetime.now().timestamp()),
                'audio_monitoring': True,
                'motion_monitoring': True,
                'location_monitoring': True,
                'geofence_monitoring': True,
                'update_frequency': 15  # seconds
            }
        )
        
        return monitoring_id
        
    except Exception as e:
        logger.error(f"Error starting location-aware monitoring: {str(e)}")
        return None

def log_emergency_event(user_id, risk_assessment, response_actions, timestamp, location_context):
    """Log emergency event with location context"""
    try:
        events_table = dynamodb.Table('SafeSakhi-EmergencyEvents')
        events_table.put_item(
            Item={
                'user_id': user_id,
                'event_id': f"{user_id}-emergency-{timestamp}",
                'timestamp': timestamp,
                'risk_assessment': risk_assessment,
                'response_actions': response_actions,
                'location_context': location_context,
                'event_type': 'emergency_response',
                'status': 'active',
                'created_at': int(datetime.now().timestamp())
            }
        )
    except Exception as e:
        logger.error(f"Error logging emergency event: {str(e)}")