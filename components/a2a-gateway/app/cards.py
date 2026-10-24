"""The public agent card of one agent: what it is and which tasks it offers, nothing about who may call it."""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from app.agent_declarations import AgentDeclaration
from app.config import Settings


def build_card(agent: AgentDeclaration, settings: Settings) -> AgentCard:
    return AgentCard(
        name=agent.title or agent.name,
        description=agent.description or f"Zuno agent {agent.name}",
        url=f"{settings.public_base_url}/agents/{agent.name}/",
        version=settings.version,
        preferred_transport="JSONRPC",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False, state_transition_history=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id=task,
                name=task.replace("-", " ").capitalize(),
                description=f"{agent.title or agent.name}: {task.replace('-', ' ')}",
                tags=[agent.name],
            )
            for task in agent.tasks
        ],
    )
