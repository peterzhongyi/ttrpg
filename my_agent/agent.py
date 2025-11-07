import json
import os
from typing import Dict
from google.adk.agents.llm_agent import Agent

# =========================================
# CONFIGURATION & SETUP
# =========================================
GAMESTATE_FILE = 'gamestate.json'

# Ensure the gamestate file exists with a default structure if it doesn't already.
if not os.path.exists(GAMESTATE_FILE):
    initial_state = {
        "player": {"name": "Unknown", "class": "Unknown", "hp": 0, "max_hp": 0, "ac": 0, "location": "Triboar Trail"},
        "combat": {"active": False, "round": 0, "initiative_order": [], "enemies": {}},
        "inventory": []
    }
    with open(GAMESTATE_FILE, 'w') as f:
        json.dump(initial_state, f, indent=2)

# =========================================
# TOOL DEFINITIONS (Game Logic)
# =========================================

def initialize_player(name: str, race: str, char_class: str, background: str, max_hp: int, ac: int) -> str:
    """
    Sets the permanent character details after creation is complete.
    Args:
        name: Character's chosen name.
        race: Character's race.
        char_class: Character's class.
        background: Character's background.
        max_hp: Calculated standard Level 1 Max HP (e.g., Fighter = 10 + CON mod).
        ac: Starting Armor Class based on standard starting equipment (e.g., Chain Mail = 16).
    """
    state = _load_state()
    state['player'].update({
        "name": name,
        "race": race,
        "class": char_class,
        "background": background,
        "hp": max_hp,
        "max_hp": max_hp,
        "ac": ac
    })
    _save_state(state)
    return f"Player {name} (Race: {race}, Class: {char_class}) initialized with {max_hp} HP and {ac} AC."

def add_to_inventory(items: list[str]) -> str:
    """
    Adds a list of items to the player's inventory.
    Args:
        items: A list of strings, where each string is an item name (e.g., ["8 copper pieces", "Shortbow"]).
    """
    state = _load_state()
    current_inv = state.get('inventory', [])
    current_inv.extend(items)
    state['inventory'] = current_inv
    _save_state(state)
    return f"Added to inventory: {', '.join(items)}"

# --- Helper Functions (Internal) ---
def _load_state() -> dict:
    # Define the default state structure here so it's always available
    default_state = {
        "player": {"name": "Unknown", "class": "Unknown", "hp": 0, "max_hp": 0, "ac": 0, "location": "Triboar Trail"},
        "combat": {"active": False, "round": 0, "initiative_order": [], "enemies": {}},
        "inventory": []
    }

    if not os.path.exists(GAMESTATE_FILE):
        return default_state

    try:
        with open(GAMESTATE_FILE, 'r') as f:
            state = json.load(f)
            # Safety check: if the file exists but is empty or corrupted, return default
            if not state or "player" not in state:
                 return default_state
            return state
    except (json.JSONDecodeError, IOError):
        return default_state

def _save_state(state: dict):
    with open(GAMESTATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

# --- Public Tools (Exposed to Agent) ---

def read_gamestate() -> dict:
    """
    Returns the full current game state.
    Use this at the start of every turn to check HP, active combatants, and inventory.
    """
    return _load_state()

def start_combat(enemies: Dict[str, int]) -> str:
    """
    Initializes a combat encounter.
    Args:
        enemies: A dictionary of unique enemy names and their starting HP.
                 Example: {"Goblin 1": 7, "Goblin 2": 7, "Wolf Leader": 15}
    """
    state = _load_state()
    state['combat']['active'] = True
    state['combat']['enemies'] = enemies
    _save_state(state)
    return f"Combat started with: {', '.join(enemies.keys())}."

def apply_damage(target: str, damage: int) -> str:
    """
    Applies damage to the player or an enemy. Handles death automatically.
    Args:
        target: The exact name of the target (e.g., "player", "Goblin 1").
        damage: Integer amount of damage to deal.
    """
    state = _load_state()
    combat = state.get('combat', {})

    # 1. Handle Player Damage
    if target.lower() == "player":
        # Ensure player stats exist before trying to modify them
        if 'hp' not in state['player']:
             return "Error: Player HP not initialized. Ask player for their max HP first."
        old_hp = state['player']['hp']
        new_hp = old_hp - damage
        state['player']['hp'] = new_hp
        _save_state(state)
        return f"Player took {damage} damage. HP: {old_hp} -> {new_hp}."

    # 2. Handle Enemy Damage
    elif combat.get('active') and target in combat.get('enemies', {}):
        old_hp = combat['enemies'][target]
        new_hp = old_hp - damage

        if new_hp <= 0:
            del combat['enemies'][target]
            msg = f"{target} took {damage} damage and has died!"
            if not combat['enemies']:
                combat['active'] = False
                msg += " Combat has ended."
        else:
            combat['enemies'][target] = new_hp
            msg = f"{target} took {damage} damage. HP: {old_hp} -> {new_hp}."

        _save_state(state)
        return msg

    return f"Error: Target '{target}' not found in active combat."

def end_combat() -> str:
    """Forcibly ends combat (e.g., if enemies flee or player escapes)."""
    state = _load_state()
    state['combat']['active'] = False
    state['combat']['enemies'] = {}
    _save_state(state)
    return "Combat ended manually."

# =========================================
# AGENT DEFINITION
# =========================================

DM_INSTRUCTIONS = """
You are an experienced Dungeon Master running the Lost Mines of Phandelver adventure for D&D 5th Edition.

### STATE MANAGEMENT RULES:
1.  **READ FIRST:** Always call `read_gamestate` before narrating any action in combat to check current HP.
2.  **CHARACTER CREATION:** Call `initialize_player` immediately after the player confirms their character details.
3.  **STARTING COMBAT:** Call `start_combat` immediately when a fight begins.
4.  **COMBAT ACTIONS:**
    * **Player Damage:** When the player hits, ask for damage, then call `apply_damage(target, amount)`.
    * **Enemy Turn:** For EACH enemy, YOU must simulate an attack roll, compare it to Player AC (from `read_gamestate`), and if it hits, simulate damage and call `apply_damage("player", amount)`.
5.  **LOOTING:** When the player loots enemies or finds treasure, you MUST call `add_to_inventory(["item 1", "item 2", ...])` to record it permanently.

NARRATIVE STYLE:
Immersive, sensory-driven, and fair.
"""

root_agent = Agent(
    model='gemini-2.5-flash',
    name='dungeon_master',
    description='Interactive DM with specialized state tracking for combat and inventory.',
    instruction=DM_INSTRUCTIONS,
    # Add the new tool to the list:
    tools=[read_gamestate, initialize_player, start_combat, apply_damage, end_combat, add_to_inventory]
)