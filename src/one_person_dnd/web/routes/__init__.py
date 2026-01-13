from __future__ import annotations

from fastapi import APIRouter

from . import character, game, memory, saves, setup, threads

router = APIRouter()
router.include_router(saves.router)
router.include_router(setup.router)
router.include_router(game.router)
router.include_router(memory.router)
router.include_router(threads.router)
router.include_router(character.router)

