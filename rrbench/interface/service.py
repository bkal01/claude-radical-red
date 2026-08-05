import json

from rrbench.battle.engine import start_battle, do_action
from rrbench.battle.state import BattleSession, in_battle, read_battle_state
from rrbench.emulator.emulator import Emulator
from rrbench.emulator.memory import (
    SPECIES_ABILITIES,
    SPECIES_MINIMUM_LEVEL,
    SPECIES_NAME,
    Party,
    PokemonFaintedError,
    PokemonNotInPartyError,
    data_dir,
)
from rrbench.interface.protocol import (
    render_observation,
    render_pre_battle,
    render_messages,
    render_team,
)
from rrbench.tasks import TaskSpec, TeamModification
from rrbench.team import EV_KEYS, PokemonConfig, TeamConfig


def create_emulator(task: TaskSpec) -> Emulator:
    emulator = Emulator(task.rom_path, task.save_state_path)
    emulator.load_state()
    return emulator


class BattleService:
    """
    Persistent Service that holds the state of a Task, takes in agent actions,
    and returns the corresponding output back to the agent.
    """

    def __init__(self, task: TaskSpec) -> None:
        self.task = task
        self.emu = create_emulator(task)
        self.session: BattleSession | None = None
        self.terminal_observation: dict | None = None
        self.original_team_config = TeamConfig.from_mem(self.emu.mem)
        self.active_team_config: TeamConfig | None = None

    def observe(self) -> dict:
        if self.active_team_config is None:
            return {
                "ok": True,
                "observation": {
                    "phase": "awaiting_team",
                    "level_cap": self.task.level_cap,
                    "team_size": self.task.team_size,
                },
            }
        if self.session is not None and self.session.ended:
            return {"ok": True, "observation": self.terminal_observation}

        battle_active = in_battle(self.emu.mem)
        if battle_active and self.session is not None:
            party = self.session.party
            party.refresh()
        else:
            party = Party(self.emu.mem)

        if not battle_active:
            observation = render_pre_battle(party)
        else:
            observation = render_observation(read_battle_state(self.emu.mem, party))
        return {"ok": True, "observation": observation}

    def team(self) -> dict:
        if self.active_team_config is None:
            return {
                "ok": True,
                "configured": False,
                "team_size": self.task.team_size,
                "level_cap": self.task.level_cap,
            }
        return {"ok": True, "configured": True, "team": render_team(self.active_team_config)}

    def lead(self, lead_pokemon: str) -> dict:
        if self.active_team_config is None:
            return {"ok": False, "error": "apply-team must configure a valid team before lead"}
        if self.session is not None or in_battle(self.emu.mem):
            return {"ok": False, "error": "lead is only valid in no_battle phase"}

        party = Party(self.emu.mem)
        try:
            self.session, state, messages = start_battle(self.emu, party, lead_pokemon)
        except PokemonNotInPartyError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "messages": render_messages(messages),
            "observation": render_observation(state),
            "ended": self.session.ended,
            "won": self.session.won,
        }

    def action(self, command: str) -> dict:
        if self.session is None or self.session.ended or not in_battle(self.emu.mem):
            return {"ok": False, "error": "action is only valid in a live battle"}

        command_parts = command.strip().split(maxsplit=1)
        if len(command_parts) != 2 or not command_parts[1]:
            return {"ok": False, "error": "action must be FIGHT, SWITCH, or SEND followed by a name"}

        action_type, action_arg = command_parts
        if action_type not in {"FIGHT", "SWITCH", "SEND"}:
            return {"ok": False, "error": f"unknown action type: {action_type!r}"}

        party = self.session.party
        party.refresh()
        state = read_battle_state(self.emu.mem, party)

        if state.needs_replacement and action_type != "SEND":
            return {"ok": False, "error": "SEND is required when the active Pokemon has fainted"}
        if not state.needs_replacement and action_type == "SEND":
            return {"ok": False, "error": "SEND is only valid when the active Pokemon has fainted"}

        if action_type == "FIGHT":
            active = party.members[state.active_slot]
            if action_arg not in active.moves:
                return {"ok": False, "error": f"{active.name} does not know {action_arg!r}"}
            move_slot = active.moves.index(action_arg)
            if active.pp[move_slot] == 0:
                return {"ok": False, "error": f"{active.name} has no PP remaining for {action_arg!r}"}
        else:
            if action_type == "SWITCH" and action_arg == party.members[state.active_slot].name:
                return {"ok": False, "error": "cannot switch to the active Pokemon"}
            try:
                party.resolve_switch_target(action_arg)
            except (PokemonNotInPartyError, PokemonFaintedError) as error:
                return {"ok": False, "error": str(error)}

        self.session, state, step_log = do_action(
            self.emu,
            self.session.party,
            self.session,
            action_type,
            action_arg,
        )
        observation = render_observation(state)
        if self.session.ended:
            observation["phase"] = "ended"
            observation["won"] = self.session.won
            self.terminal_observation = observation
        return {
            "ok": True,
            "messages": render_messages(step_log.messages),
            "observation": observation,
            "ended": self.session.ended,
            "won": self.session.won,
        }

    def reset(self) -> dict:
        if self.active_team_config is None:
            return {"ok": False, "error": "apply-team must configure a valid team before reset"}
        self.emu.load_state()
        self.active_team_config.apply(self.emu.mem)
        self.session = None
        self.terminal_observation = None
        return self.observe()

    def apply_team(self, team: dict) -> dict:
        """
        we expect `team` to look like this:

        {
            "members": [
                {
                    "slot": 0,
                    "species_id": 727,
                    "evs": {"HP": 252, "ATK": 0, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 252}
                },
                {
                    "slot": 1,
                    "species_id": 983,
                    "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0}
                },
                {
                    "slot": 2,
                    "species_id": 303,
                    "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0}
                },
                {
                    "slot": 3,
                    "species_id": 763,
                    "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0}
                },
                {
                    "slot": 4,
                    "species_id": 936,
                    "evs": {"HP": 252, "ATK": 0, "DEF": 4, "SPE": 0, "SPA": 252, "SPDEF": 0}
                },
                {
                    "slot": 5,
                    "species_id": 130,
                    "evs": {"HP": 252, "ATK": 252, "DEF": 4, "SPE": 0, "SPA": 0, "SPDEF": 0}
                }
            ]
        }

        the TaskSpec determines what team modifications are allowed, and we enforce them accordingly.
        """
        initializing = (
            self.active_team_config is None
            and self.session is None
            and not in_battle(self.emu.mem)
        )
        modifications = frozenset(TeamModification) if initializing else self.task.allowed_team_modifications
        if not initializing and not modifications:
            return {"ok": False, "error": "team updates are not allowed for this task"}
        if (
            TeamModification.EVS not in modifications
            and TeamModification.ABILITIES not in modifications
            and TeamModification.MOVES not in modifications
            and TeamModification.ITEMS not in modifications
            and TeamModification.POKEMON not in modifications
        ):
            return {"ok": False, "error": "team updates are not allowed for this task"}
        if not isinstance(team, dict):
            return {"ok": False, "error": "team must be an object"}
        if set(team) != {"members"}:
            return {"ok": False, "error": "team must contain only members"}
        members_value = team.get("members")
        if isinstance(members_value, list):
            if TeamModification.EVS not in modifications and any(
                isinstance(member, dict) and "evs" in member
                for member in members_value
            ):
                return {"ok": False, "error": "updating EVs is not allowed for this task"}
            if TeamModification.ABILITIES not in modifications and any(
                isinstance(member, dict) and "ability_id" in member
                for member in members_value
            ):
                return {"ok": False, "error": "updating Abilities is not allowed for this task"}
            if TeamModification.MOVES not in modifications and any(
                isinstance(member, dict) and "move_ids" in member
                for member in members_value
            ):
                return {"ok": False, "error": "updating moves is not allowed for this task"}
            if TeamModification.ITEMS not in modifications and any(
                isinstance(member, dict) and "held_item_id" in member
                for member in members_value
            ):
                return {"ok": False, "error": "updating items is not allowed for this task"}
        if not initializing and (self.session is None or self.session.won):
            return {"ok": False, "error": "apply-team is only valid in a live battle or after a lost episode"}
        if not initializing and not self.session.ended and not in_battle(self.emu.mem):
            return {"ok": False, "error": "apply-team is only valid in a live battle or after a lost episode"}
        members = team["members"]
        current_team_config = self.active_team_config or self.original_team_config
        expected_team_size = self.task.team_size if initializing else len(current_team_config.members)
        if not isinstance(members, list) or len(members) != expected_team_size:
            return {"ok": False, "error": "team must contain every required team member"}
        items = []
        if TeamModification.ITEMS in modifications:
            items = json.loads((data_dir / "items.json").read_text())
        learnsets = []
        if TeamModification.MOVES in modifications:
            learnsets = json.loads((data_dir / "learnsets.json").read_text())

        updated_members = {}
        for member in members:
            expected_fields = {"slot", "species_id"}
            if TeamModification.EVS in modifications:
                expected_fields.add("evs")
            if TeamModification.ABILITIES in modifications:
                expected_fields.add("ability_id")
            if TeamModification.MOVES in modifications:
                expected_fields.add("move_ids")
            if TeamModification.ITEMS in modifications:
                expected_fields.add("held_item_id")
            if not isinstance(member, dict) or set(member) != expected_fields:
                fields = ", ".join(sorted(expected_fields))
                return {"ok": False, "error": f"each member must contain only {fields}"}
            slot = member["slot"]
            if type(slot) is not int or slot not in range(expected_team_size):
                return {"ok": False, "error": "each member must use a valid team slot"}
            if slot in updated_members:
                return {"ok": False, "error": "team members must use each team slot once"}
            species_id = member["species_id"]
            if type(species_id) is not int or species_id not in SPECIES_NAME:
                return {"ok": False, "error": "species_id must be a valid Pokemon ID"}
            if SPECIES_MINIMUM_LEVEL[species_id] > self.task.level_cap:
                return {
                    "ok": False,
                    "error": "species_id must be available at the task level cap",
                }
            if (
                TeamModification.POKEMON not in modifications
                and species_id != current_team_config.members[slot].species_id
            ):
                return {"ok": False, "error": "species_id must match the active team member at its slot"}

            current_member = current_team_config.members[slot]
            nature_id = 0 if initializing else current_member.nature_id
            evs = dict(current_member.evs)
            if "evs" in member:
                evs = member["evs"]
                if not isinstance(evs, dict) or set(evs) != set(EV_KEYS):
                    return {"ok": False, "error": "each member must specify exactly HP, ATK, DEF, SPE, SPA, and SPDEF EVs"}
                if any(type(ev) is not int or ev < 0 or ev > 252 or ev % 4 for ev in evs.values()):
                    return {"ok": False, "error": "EVs must be integers from 0 through 252 in multiples of four"}
                if sum(evs.values()) > 508:
                    return {"ok": False, "error": "each Pokemon may have at most 508 total EVs"}

            ability_id = current_member.ability_id
            if "ability_id" in member:
                ability_id = member["ability_id"]
                species_abilities = SPECIES_ABILITIES.get(species_id, {})
                valid_abilities = set(species_abilities.get("normal", []))
                hidden_ability = species_abilities.get("hidden")
                if hidden_ability is not None:
                    valid_abilities.add(hidden_ability)
                if type(ability_id) is not int or ability_id not in valid_abilities:
                    return {"ok": False, "error": "ability_id must be a valid ability for the active Pokemon"}

            move_ids = current_member.move_ids
            if "move_ids" in member:
                move_ids = member["move_ids"]
                if not isinstance(move_ids, list) or len(move_ids) != 4 or any(
                    type(move_id) is not int for move_id in move_ids
                ):
                    return {"ok": False, "error": "move_ids must contain exactly four integer move IDs"}
                valid_move_ids = set()
                seen_species_ids = set()
                pending_species_ids = [species_id]
                while pending_species_ids:
                    current_species_id = pending_species_ids.pop()
                    if current_species_id in seen_species_ids:
                        continue
                    seen_species_ids.add(current_species_id)
                    learnset = learnsets[current_species_id]
                    valid_move_ids.update(
                        entry["move_id"]
                        for entry in learnset["level_up"]
                        if entry["level"] <= self.task.level_cap
                    )
                    for source in ("tm_hm", "tutor", "egg", "pre_evolution", "event"):
                        valid_move_ids.update(learnset[source])
                    pending_species_ids.extend(learnset.get("pre_evolution_ids", []))
                if any(move_id not in valid_move_ids for move_id in move_ids):
                    return {
                        "ok": False,
                        "error": "each move_id must be learnable by the active Pokemon at the task level cap",
                    }

            held_item = current_member.held_item
            if "held_item_id" in member:
                held_item = member["held_item_id"]
                if (
                    type(held_item) is not int
                    or held_item < 0
                    or held_item >= len(items)
                    or held_item != 0 and items[held_item] is None
                ):
                    return {"ok": False, "error": "held_item_id must be a valid item ID"}

            updated_members[slot] = PokemonConfig(
                species_id=species_id,
                evs=dict(evs),
                level=self.task.level_cap if initializing else current_member.level,
                nature_id=nature_id,
                ability_id=ability_id,
                held_item=held_item,
                move_ids=tuple(move_ids) if move_ids is not None else None,
            )

        self.active_team_config = TeamConfig(
            members=[updated_members[slot] for slot in range(expected_team_size)]
        )
        return {"ok": True, "team": render_team(self.active_team_config)}
