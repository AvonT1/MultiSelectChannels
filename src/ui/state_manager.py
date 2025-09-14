"""
State management for user interactions and multi-step operations.
Handles conversation state, input validation, and workflow management.
"""
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class UserState(Enum):
    """User conversation states."""
    IDLE = "idle"
    
    # Channel management states
    ADDING_CHANNEL = "adding_channel"
    EDITING_CHANNEL = "editing_channel"
    CHANNEL_TITLE_INPUT = "channel_title_input"
    CHANNEL_ID_INPUT = "channel_id_input"
    
    # Mapping management states
    CREATING_MAPPING = "creating_mapping"
    MAPPING_SOURCE_SELECT = "mapping_source_select"
    MAPPING_DEST_SELECT = "mapping_dest_select"
    MAPPING_MODE_SELECT = "mapping_mode_select"
    
    # Multi-select operations
    MULTI_SELECT_CHANNELS = "multi_select_channels"
    MULTI_SELECT_MAPPINGS = "multi_select_mappings"
    
    # Admin operations
    ADMIN_USER_INPUT = "admin_user_input"
    ADMIN_CLEANUP_CONFIRM = "admin_cleanup_confirm"
    
    # Setup and configuration
    SETUP_WELCOME = "setup_welcome"
    SETUP_CHANNELS = "setup_channels"
    SETUP_MAPPINGS = "setup_mappings"
    SETUP_COMPLETE = "setup_complete"
    
    # Input validation states
    WAITING_FOR_INPUT = "waiting_for_input"
    VALIDATING_INPUT = "validating_input"


@dataclass
class StateData:
    """Data associated with a user's current state."""
    state: UserState = UserState.IDLE
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    step: int = 0
    max_steps: int = 1
    
    def is_expired(self) -> bool:
        """Check if the state has expired."""
        return self.expires_at is not None and datetime.utcnow() > self.expires_at
    
    def set_expiry(self, minutes: int = 30):
        """Set state expiry time."""
        self.expires_at = datetime.utcnow() + timedelta(minutes=minutes)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get data value with default."""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set data value."""
        self.data[key] = value
    
    def update(self, **kwargs):
        """Update multiple data values."""
        self.data.update(kwargs)


class StateManager:
    """Manages user conversation states and multi-step operations."""
    
    def __init__(self):
        self._user_states: Dict[int, StateData] = {}
        self._state_handlers: Dict[UserState, Callable] = {}
        self._input_validators: Dict[str, Callable] = {}
    
    def get_user_state(self, user_id: int) -> StateData:
        """Get current state for a user."""
        if user_id not in self._user_states:
            self._user_states[user_id] = StateData()
        
        state_data = self._user_states[user_id]
        
        # Clean up expired states
        if state_data.is_expired():
            self.clear_user_state(user_id)
            state_data = StateData()
            self._user_states[user_id] = state_data
        
        return state_data
    
    def set_user_state(self, user_id: int, state: UserState, 
                      data: Optional[Dict[str, Any]] = None,
                      expiry_minutes: int = 30) -> StateData:
        """Set user state with optional data and expiry."""
        state_data = StateData(
            state=state,
            data=data or {},
            created_at=datetime.utcnow()
        )
        state_data.set_expiry(expiry_minutes)
        
        self._user_states[user_id] = state_data
        logger.debug(f"Set user {user_id} state to {state.value}")
        
        return state_data
    
    def update_user_state(self, user_id: int, **data) -> StateData:
        """Update user state data."""
        state_data = self.get_user_state(user_id)
        state_data.update(**data)
        return state_data
    
    def clear_user_state(self, user_id: int):
        """Clear user state and return to idle."""
        if user_id in self._user_states:
            del self._user_states[user_id]
        logger.debug(f"Cleared state for user {user_id}")
    
    def is_user_in_state(self, user_id: int, state: UserState) -> bool:
        """Check if user is in a specific state."""
        current_state = self.get_user_state(user_id)
        return current_state.state == state
    
    def advance_step(self, user_id: int) -> StateData:
        """Advance to next step in multi-step operation."""
        state_data = self.get_user_state(user_id)
        state_data.step += 1
        return state_data
    
    def is_final_step(self, user_id: int) -> bool:
        """Check if user is on the final step."""
        state_data = self.get_user_state(user_id)
        return state_data.step >= state_data.max_steps - 1
    
    # Channel management state helpers
    def start_channel_creation(self, user_id: int) -> StateData:
        """Start channel creation workflow."""
        return self.set_user_state(
            user_id, 
            UserState.ADDING_CHANNEL,
            data={
                'step': 'id_input',
                'channel_data': {}
            }
        )
    
    def start_channel_editing(self, user_id: int, channel_id: int) -> StateData:
        """Start channel editing workflow."""
        return self.set_user_state(
            user_id,
            UserState.EDITING_CHANNEL,
            data={
                'channel_id': channel_id,
                'step': 'menu',
                'changes': {}
            }
        )
    
    # Mapping management state helpers
    def start_mapping_creation(self, user_id: int) -> StateData:
        """Start mapping creation workflow."""
        return self.set_user_state(
            user_id,
            UserState.CREATING_MAPPING,
            data={
                'step': 'source_select',
                'mapping_data': {},
                'selected_sources': [],
                'selected_destinations': []
            }
        )
    
    def set_mapping_sources(self, user_id: int, source_ids: List[int]) -> StateData:
        """Set selected source channels for mapping creation."""
        state_data = self.get_user_state(user_id)
        state_data.set('selected_sources', source_ids)
        state_data.set('step', 'dest_select')
        return state_data
    
    def set_mapping_destinations(self, user_id: int, dest_ids: List[int]) -> StateData:
        """Set selected destination channels for mapping creation."""
        state_data = self.get_user_state(user_id)
        state_data.set('selected_destinations', dest_ids)
        state_data.set('step', 'mode_select')
        return state_data
    
    # Multi-select state helpers
    def start_multi_select(self, user_id: int, operation: str, 
                          available_items: List[Dict[str, Any]]) -> StateData:
        """Start multi-select operation."""
        return self.set_user_state(
            user_id,
            UserState.MULTI_SELECT_CHANNELS if 'channel' in operation else UserState.MULTI_SELECT_MAPPINGS,
            data={
                'operation': operation,
                'available_items': available_items,
                'selected_ids': [],
                'page': 0
            }
        )
    
    def toggle_selection(self, user_id: int, item_id: int) -> StateData:
        """Toggle item selection in multi-select mode."""
        state_data = self.get_user_state(user_id)
        selected_ids = state_data.get('selected_ids', [])
        
        if item_id in selected_ids:
            selected_ids.remove(item_id)
        else:
            selected_ids.append(item_id)
        
        state_data.set('selected_ids', selected_ids)
        return state_data
    
    def select_all_items(self, user_id: int) -> StateData:
        """Select all available items."""
        state_data = self.get_user_state(user_id)
        available_items = state_data.get('available_items', [])
        all_ids = [item['id'] for item in available_items]
        state_data.set('selected_ids', all_ids)
        return state_data
    
    def select_no_items(self, user_id: int) -> StateData:
        """Deselect all items."""
        state_data = self.get_user_state(user_id)
        state_data.set('selected_ids', [])
        return state_data
    
    # Setup workflow helpers
    def start_setup_workflow(self, user_id: int) -> StateData:
        """Start initial setup workflow for new users."""
        return self.set_user_state(
            user_id,
            UserState.SETUP_WELCOME,
            data={
                'setup_step': 0,
                'setup_data': {},
                'completed_steps': []
            },
            expiry_minutes=60  # Longer expiry for setup
        )
    
    def advance_setup_step(self, user_id: int) -> StateData:
        """Advance to next setup step."""
        state_data = self.get_user_state(user_id)
        current_step = state_data.get('setup_step', 0)
        
        # Mark current step as completed
        completed_steps = state_data.get('completed_steps', [])
        if current_step not in completed_steps:
            completed_steps.append(current_step)
            state_data.set('completed_steps', completed_steps)
        
        # Advance to next step
        next_step = current_step + 1
        state_data.set('setup_step', next_step)
        
        # Update state based on step
        if next_step == 1:
            state_data.state = UserState.SETUP_CHANNELS
        elif next_step == 2:
            state_data.state = UserState.SETUP_MAPPINGS
        elif next_step >= 3:
            state_data.state = UserState.SETUP_COMPLETE
        
        return state_data
    
    # Input validation helpers
    def start_input_collection(self, user_id: int, input_type: str, 
                             prompt: str, validator: Optional[str] = None) -> StateData:
        """Start collecting user input with validation."""
        return self.set_user_state(
            user_id,
            UserState.WAITING_FOR_INPUT,
            data={
                'input_type': input_type,
                'prompt': prompt,
                'validator': validator,
                'attempts': 0,
                'max_attempts': 3
            }
        )
    
    def validate_input(self, user_id: int, input_value: str) -> tuple[bool, Optional[str]]:
        """Validate user input based on current state."""
        state_data = self.get_user_state(user_id)
        
        if state_data.state != UserState.WAITING_FOR_INPUT:
            return False, "Not waiting for input"
        
        validator_name = state_data.get('validator')
        if validator_name and validator_name in self._input_validators:
            validator = self._input_validators[validator_name]
            return validator(input_value)
        
        # Default validation (non-empty)
        if input_value.strip():
            return True, None
        else:
            return False, "Input cannot be empty"
    
    def register_input_validator(self, name: str, validator: Callable[[str], tuple[bool, Optional[str]]]):
        """Register a custom input validator."""
        self._input_validators[name] = validator
    
    # State persistence helpers (for Redis storage)
    def serialize_state(self, user_id: int) -> Optional[str]:
        """Serialize user state to JSON string."""
        if user_id not in self._user_states:
            return None
        
        state_data = self._user_states[user_id]
        
        serializable_data = {
            'state': state_data.state.value,
            'data': state_data.data,
            'created_at': state_data.created_at.isoformat(),
            'expires_at': state_data.expires_at.isoformat() if state_data.expires_at else None,
            'step': state_data.step,
            'max_steps': state_data.max_steps
        }
        
        return json.dumps(serializable_data)
    
    def deserialize_state(self, user_id: int, serialized_data: str) -> StateData:
        """Deserialize user state from JSON string."""
        try:
            data = json.loads(serialized_data)
            
            state_data = StateData(
                state=UserState(data['state']),
                data=data['data'],
                created_at=datetime.fromisoformat(data['created_at']),
                expires_at=datetime.fromisoformat(data['expires_at']) if data['expires_at'] else None,
                step=data['step'],
                max_steps=data['max_steps']
            )
            
            self._user_states[user_id] = state_data
            return state_data
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to deserialize state for user {user_id}: {e}")
            # Return default state on error
            return self.get_user_state(user_id)
    
    # Cleanup and maintenance
    def cleanup_expired_states(self):
        """Remove expired user states."""
        expired_users = []
        
        for user_id, state_data in self._user_states.items():
            if state_data.is_expired():
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del self._user_states[user_id]
            logger.debug(f"Cleaned up expired state for user {user_id}")
        
        return len(expired_users)
    
    def get_active_states_count(self) -> int:
        """Get count of active user states."""
        return len(self._user_states)
    
    def get_states_by_type(self, state: UserState) -> List[int]:
        """Get list of user IDs in a specific state."""
        return [
            user_id for user_id, state_data in self._user_states.items()
            if state_data.state == state and not state_data.is_expired()
        ]


# Default input validators
def validate_telegram_id(input_value: str) -> tuple[bool, Optional[str]]:
    """Validate Telegram ID input."""
    try:
        telegram_id = int(input_value.strip())
        if telegram_id > 0:
            return True, None
        else:
            return False, "Telegram ID must be a positive number"
    except ValueError:
        return False, "Please enter a valid number"


def validate_channel_title(input_value: str) -> tuple[bool, Optional[str]]:
    """Validate channel title input."""
    title = input_value.strip()
    if len(title) < 1:
        return False, "Channel title cannot be empty"
    elif len(title) > 100:
        return False, "Channel title must be less than 100 characters"
    else:
        return True, None


def validate_non_empty(input_value: str) -> tuple[bool, Optional[str]]:
    """Validate non-empty input."""
    if input_value.strip():
        return True, None
    else:
        return False, "Input cannot be empty"


# Global state manager instance
state_manager = StateManager()

# Register default validators
state_manager.register_input_validator('telegram_id', validate_telegram_id)
state_manager.register_input_validator('channel_title', validate_channel_title)
state_manager.register_input_validator('non_empty', validate_non_empty)
