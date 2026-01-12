from __future__ import annotations

from fastapi import APIRouter

from . import game, memory, saves, setup

router = APIRouter()
router.include_router(saves.router)
router.include_router(setup.router)
router.include_router(game.router)
router.include_router(memory.router)

