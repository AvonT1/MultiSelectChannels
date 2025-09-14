"""
Message processor for handling different message types and content extraction.
Supports text, media, and complex message structures.
"""
import hashlib
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.clients import ClientFactory
from src.config import settings

logger = logging.getLogger(__name__)


class MessageProcessor:
    """Processes and analyzes messages for forwarding operations."""
    
    def __init__(self, client_factory: ClientFactory):
        self.client_factory = client_factory
    
    async def extract_message_data(self, source_channel_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        """Extract comprehensive message data for processing."""
        try:
            # Get message using user client (more reliable for private channels)
            messages = await self.client_factory.user_client.get_messages(source_channel_id, message_id)
            if not messages:
                logger.warning(f"Could not retrieve message {source_channel_id}:{message_id}")
                return None
            
            message_data = messages[0]
            
            # Extract message content
            extracted_data = {
                'message_id': message_data['id'],
                'source_channel_id': source_channel_id,
                'text': message_data.get('text', ''),
                'date': message_data.get('date'),
                'has_media': message_data.get('media', False),
                'from_id': message_data.get('from_id'),
                'content_hash': self._generate_content_hash(message_data),
                'message_type': self._determine_message_type(message_data),
                'extracted_at': datetime.utcnow().isoformat()
            }
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error extracting message data {source_channel_id}:{message_id}: {e}")
            return None
    
    def _generate_content_hash(self, message_data: Dict[str, Any]) -> str:
        """Generate a hash of message content for deduplication."""
        # Create a string representation of key message content
        content_parts = [
            str(message_data.get('text', '')),
            str(message_data.get('has_media', False)),
            str(message_data.get('from_id', ''))
        ]
        
        content_string = '|'.join(content_parts)
        return hashlib.sha256(content_string.encode('utf-8')).hexdigest()
    
    def _determine_message_type(self, message_data: Dict[str, Any]) -> str:
        """Determine the type of message content."""
        if message_data.get('has_media'):
            return 'media'
        elif message_data.get('text'):
            return 'text'
        else:
            return 'other'
    
    async def validate_forwarding_eligibility(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if a message is eligible for forwarding."""
        eligibility = {
            'eligible': True,
            'reasons': [],
            'warnings': []
        }
        
        # Check message age (optional limit)
        if message_data.get('date'):
            message_age = datetime.utcnow() - message_data['date']
            if message_age.days > 30:  # Example: don't forward messages older than 30 days
                eligibility['warnings'].append('Message is older than 30 days')
        
        # Check content type restrictions
        message_type = message_data.get('message_type', 'other')
        if message_type == 'other':
            eligibility['warnings'].append('Unknown message type detected')
        
        # Check for empty content
        if not message_data.get('text') and not message_data.get('has_media'):
            eligibility['eligible'] = False
            eligibility['reasons'].append('Message has no text or media content')
        
        return eligibility
    
    async def prepare_forwarding_data(self, message_data: Dict[str, Any], 
                                    dest_channel_id: int, mode: str) -> Dict[str, Any]:
        """Prepare message data for specific forwarding operation."""
        forwarding_data = {
            'source_message_id': message_data['message_id'],
            'source_channel_id': message_data['source_channel_id'],
            'dest_channel_id': dest_channel_id,
            'mode': mode,
            'prepared_at': datetime.utcnow().isoformat()
        }
        
        # Add mode-specific preparations
        if mode == 'copy':
            # For copy mode, we might need to modify content
            forwarding_data['modified_text'] = self._prepare_copy_text(message_data.get('text', ''))
        
        return forwarding_data
    
    def _prepare_copy_text(self, original_text: str) -> str:
        """Prepare text for copy mode (remove/modify certain elements)."""
        # Remove or modify elements that shouldn't be copied
        # This is a placeholder for more sophisticated text processing
        
        # Example: Remove certain patterns, URLs, mentions, etc.
        processed_text = original_text
        
        # Add any necessary modifications here
        
        return processed_text
    
    async def analyze_message_content(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze message content for insights and metadata."""
        analysis = {
            'word_count': 0,
            'has_urls': False,
            'has_mentions': False,
            'has_hashtags': False,
            'language': 'unknown',
            'sentiment': 'neutral'
        }
        
        text = message_data.get('text', '')
        if text:
            # Basic text analysis
            analysis['word_count'] = len(text.split())
            analysis['has_urls'] = 'http' in text.lower() or 'www.' in text.lower()
            analysis['has_mentions'] = '@' in text
            analysis['has_hashtags'] = '#' in text
            
            # More sophisticated analysis could be added here
            # (language detection, sentiment analysis, etc.)
        
        return analysis
