/** Web Worker entry: the rollout lookahead off the main thread. Protocol in lib/rollout.ts. */
import { handleMessage, type WorkerRequest, type WorkerResponse } from '../lib/rollout'

self.onmessage = (e: MessageEvent<WorkerRequest>) => {
  handleMessage(e.data, (out: WorkerResponse) => self.postMessage(out))
}
