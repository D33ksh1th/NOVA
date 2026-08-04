import { AnimationController } from "./AnimationController";
import { BehaviorController } from "./BehaviorController";
import { EmotionController } from "./EmotionController";
import { EyeTrackingController } from "./EyeTrackingController";
import { LipSyncController } from "./LipSyncController";
import { SpeechBubbleController } from "./SpeechBubbleController";
import { StateMachine } from "./StateMachine";
import type { AvatarBrainEvent, AvatarEngineSnapshot } from "./types";

export class AvatarController {
  private readonly stateMachine = new StateMachine();
  private readonly emotionController = new EmotionController();
  private readonly animationController = new AnimationController();
  private readonly behaviorController = new BehaviorController();
  private readonly speechBubbleController = new SpeechBubbleController();
  private readonly eyeTrackingController = new EyeTrackingController();
  private readonly lipSyncController = new LipSyncController();

  private snapshot: AvatarEngineSnapshot = {
    state: "idle",
    emotion: "neutral",
    speechText: null,
    animationOverride: null,
    eyeTarget: "ambient",
    lastEvent: "snapshot",
  };

  reset() {
    this.stateMachine.reset();
    this.emotionController.reset();
    this.animationController.reset();
    this.behaviorController.reset();
    this.speechBubbleController.reset();
    this.eyeTrackingController.reset();
    this.lipSyncController.reset();

    this.snapshot = {
      state: "idle",
      emotion: "neutral",
      speechText: null,
      animationOverride: null,
      eyeTarget: "ambient",
      lastEvent: "snapshot",
    };

    return this.snapshot;
  }

  reduce(event: AvatarBrainEvent) {
    const nextState = this.stateMachine.transition(event.name, event.payload?.state);
    const nextEmotion = this.emotionController.update(event);
    const speechText = this.speechBubbleController.update(event);
    const eyeTarget = this.eyeTrackingController.update(event);

    this.lipSyncController.onEvent(event);

    const behaviorClip = this.behaviorController.update(event, nextState);
    const baseClip = this.animationController.choose(nextState, nextEmotion, event.name);

    this.snapshot = {
      state: nextState,
      emotion: nextEmotion,
      speechText,
      animationOverride: behaviorClip ?? baseClip,
      eyeTarget,
      lastEvent: event.name,
    };

    return this.snapshot;
  }

  getSnapshot() {
    return this.snapshot;
  }
}
