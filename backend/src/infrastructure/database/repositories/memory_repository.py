"""
Memory Repository - Data access layer for long-term memory.

This module provides database access for storing and retrieving
user memories that persist between sessions.
"""

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import MemoryModel

logger = logging.getLogger(__name__)


class MemoryRepository:
    """
    Repository for managing user memories in the database.

    Provides async methods to add, retrieve, and delete memories.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize the memory repository.

        Args:
            session: AsyncSession for database operations
        """
        self.session = session

    async def add_memory(self, content: str, source: str = "user") -> MemoryModel:
        """
        Add a new memory to the database.

        Args:
            content: The fact to remember
            source: Source of memory ("user" or "auto")

        Returns:
            Created MemoryModel instance
        """
        memory = MemoryModel(content=content, source=source)
        self.session.add(memory)
        await self.session.flush()
        logger.info(f"Memory added: '{content[:50]}...' (source={source})")
        return memory

    async def get_all_memories(self) -> List[MemoryModel]:
        """
        Retrieve all memories from the database.

        Returns:
            List of MemoryModel instances
        """
        stmt = select(MemoryModel).order_by(MemoryModel.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_all_memories(self) -> int:
        """
        Delete all memories from the database.

        Returns:
            Number of memories deleted
        """
        stmt = select(MemoryModel)
        result = await self.session.execute(stmt)
        memories = result.scalars().all()
        count = len(memories)

        for memory in memories:
            await self.session.delete(memory)

        logger.info(f"Deleted {count} memories")
        return count

    async def delete_memory(self, memory_id: int) -> bool:
        """
        Delete a specific memory by ID.

        Args:
            memory_id: ID of the memory to delete

        Returns:
            True if deleted, False if not found
        """
        stmt = select(MemoryModel).where(MemoryModel.id == memory_id)
        result = await self.session.execute(stmt)
        memory = result.scalar_one_or_none()

        if memory:
            await self.session.delete(memory)
            logger.info(f"Memory {memory_id} deleted")
            return True

        logger.warning(f"Memory {memory_id} not found")
        return False
