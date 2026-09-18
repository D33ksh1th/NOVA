type Listener<T> = (event: T) => void;

export class EventBus<T extends { name: string }> {
  private readonly listeners = new Map<string, Set<Listener<T>>>();

  on(eventName: T["name"], listener: Listener<T>) {
    const key = String(eventName);
    const pool = this.listeners.get(key) ?? new Set<Listener<T>>();
    pool.add(listener);
    this.listeners.set(key, pool);

    return () => {
      pool.delete(listener);
      if (!pool.size) {
        this.listeners.delete(key);
      }
    };
  }

  emit(event: T) {
    const pool = this.listeners.get(String(event.name));
    if (!pool) {
      return;
    }
    pool.forEach((listener) => listener(event));
  }

  clear() {
    this.listeners.clear();
  }
}
