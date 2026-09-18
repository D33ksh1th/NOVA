from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from services.gateway.agent_status import require_local
from services.tools.apple_music import apple_music


router = APIRouter(prefix="/api/music", dependencies=[Depends(require_local)])


class MusicControl(BaseModel):
    operation: Literal["pause", "resume", "next", "previous"]


@router.get("/status")
def music_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return apple_music.run()


@router.post("/control")
def music_control(body: MusicControl, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return apple_music.run(body.operation)