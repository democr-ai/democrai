type QueueItem = {
  priority: number;
  seq: number;
  data: any;
};

export type InboundMessagePriorityFn = (data: any) => number;
export type InboundDispatchFn = (data: any) => void;

export class InboundController {
  private readonly queue: QueueItem[] = [];

  private queueDirty = false;

  private seq = 0;

  private drainTimer: number | null = null;

  private bootGateTimer: number | null = null;

  private bootGateOpen: boolean;

  private readonly gateInbound: boolean;

  private readonly maxPerTick: number;

  private readonly priorityFn: InboundMessagePriorityFn;

  private readonly dispatchFn: InboundDispatchFn;

  constructor({
    maxPerTick = 120,
    gateInbound = false,
    priorityFn,
    dispatchFn,
  }: {
    maxPerTick?: number;
    gateInbound?: boolean;
    priorityFn: InboundMessagePriorityFn;
    dispatchFn: InboundDispatchFn;
  }) {
    this.maxPerTick = maxPerTick;
    this.gateInbound = gateInbound;
    this.bootGateOpen = !gateInbound;
    this.priorityFn = priorityFn;
    this.dispatchFn = dispatchFn;

    if (gateInbound) {
      this.bootGateTimer = window.setTimeout(() => {
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => {
            this.bootGateOpen = true;
            this.scheduleDrain();
          });
        });
      }, 0);
    }
  }

  enqueue(data: any): void {
    this.queue.push({
      priority: this.priorityFn(data),
      seq: this.seq,
      data,
    });
    this.queueDirty = true;
    this.seq += 1;

    this.scheduleDrain();
  }

  private scheduleDrain(): void {
    if (!this.bootGateOpen || this.drainTimer != null) return;
    if (this.gateInbound) {
      this.drainTimer = window.requestAnimationFrame(() => this.drain());
    } else {
      this.drainTimer = window.setTimeout(() => this.drain(), 0);
    }
  }

  drain(): void {
    this.drainTimer = null;
    if (this.queueDirty) {
      this.queue.sort((a, b) => (a.priority - b.priority) || (a.seq - b.seq));
      this.queueDirty = false;
    }

    let processed = 0;
    while (this.queue.length > 0 && processed < this.maxPerTick) {
      const item = this.queue.shift();
      if (item) this.dispatchFn(item.data);
      processed += 1;
    }

    if (this.queue.length > 0) {
      this.scheduleDrain();
    }
  }

  dispose(): void {
    if (this.drainTimer != null) {
      if (this.gateInbound) window.cancelAnimationFrame(this.drainTimer);
      else window.clearTimeout(this.drainTimer);
      this.drainTimer = null;
    }
    if (this.bootGateTimer != null) {
      window.clearTimeout(this.bootGateTimer);
      this.bootGateTimer = null;
    }
    this.queue.length = 0;
    this.queueDirty = false;
  }
}
