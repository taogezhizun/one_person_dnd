from __future__ import annotations

from fastapi import APIRouter

from . import character, cheats, game, locale, memory, models, new_adventure, saves, setup, threads

router = APIRouter()
router.include_router(locale.router)
router.include_router(saves.router)
router.include_router(setup.router)
router.include_router(game.router)
router.include_router(memory.router)
router.include_router(threads.router)
router.include_router(character.router)
router.include_router(cheats.router)
router.include_router(models.router)
router.include_router(new_adventure.router)
