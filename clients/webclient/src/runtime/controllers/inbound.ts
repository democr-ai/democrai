type QueueItem = {
  priority: number;
  seq: number;
  data: any;
};

export type InboundMessagePriorityFn = (data: any) => number;
export type InboundDispatchFn = (data: any) => void;

export class InboundController {
  private readonly queue: QueueItem[] = [];

  private seq = 0;

  private drainTimer: number | null = null;

  private readonly maxPerTick: number;

  private readonly priorityFn: InboundMessagePriorityFn;

  private readonly dispatchFn: InboundDispatchFn;

  constructor({
    maxPerTick = 120,
    priorityFn,
    dispatchFn,
  }: {
    maxPerTick?: number;
    priorityFn: InboundMessagePriorityFn;
    dispatchFn: InboundDispatchFn;
  }) {
    this.maxPerTick = maxPerTick;
    this.priorityFn = priorityFn;
    this.dispatchFn = dispatchFn;
  }

  enqueue(data: any): void {
    this.queue.push({
      priority: this.priorityFn(data),
      seq: this.seq,
      data,
    });
    this.seq += 1;

    if (this.drainTimer == null) {
      this.drainTimer = window.setTimeout(() => this.drain(), 0);
    }
  }

  drain(): void {
    this.drainTimer = null;
    this.queue.sort((a, b) => (a.priority - b.priority) || (a.seq - b.seq));

    let processed = 0;
    while (this.queue.length > 0 && processed < this.maxPerTick) {
      const item = this.queue.shift();
      if (item) this.dispatchFn(item.data);
      processed += 1;
    }

    if (this.queue.length > 0) {
      this.drainTimer = window.setTimeout(() => this.drain(), 0);
    }
  }

  dispose(): void {
    if (this.drainTimer != null) {
      window.clearTimeout(this.drainTimer);
      this.drainTimer = null;
    }
    this.queue.length = 0;
  }
}
