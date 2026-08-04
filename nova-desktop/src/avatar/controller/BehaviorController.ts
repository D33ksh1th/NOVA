import type { AvatarState } from "@/types";
import type { AvatarBrainEvent } from "./types";

export class BehaviorController {
  private idleCounter = 0;

  reset() {
    this.idleCounter = 0;
  }

  update(event: AvatarBrainEvent, state: AvatarState) {
    if (event.name === "idle_tick") {
      this.idleCounter += 1;
    } else {
      this.idleCounter = 0;
    }

    if (state === "idle") {
      if (this.idleCounter >= 8) {
        return "NOVA_Sleep";
      }
      if (this.idleCounter >= 4) {
        return "NOVA_Observe_User";
      }
      if (this.idleCounter >= 2) {
        return "NOVA_Look_Around";
      }
    }

    return null;
  }
}
