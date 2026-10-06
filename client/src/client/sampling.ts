export const EFFORTS = ["low", "high", "max"] as const;

export type Effort = (typeof EFFORTS)[number];

export type Sampling = {
  reasoning_effort: Effort;
  temperature: number;
  top_p: number;
};

export const DEFAULT_SAMPLING: Sampling = {
  reasoning_effort: "max",
  temperature: 1,
  top_p: 0.95,
};

export function samplingFromInputs(effort: string, temperature: number, topP: number): Sampling {
  if (effort !== "low" && effort !== "high" && effort !== "max") {
    throw new Error("思考力度只能是 low、high、max。恢复：在对话框里重选一档再发。");
  }
  if (!(temperature >= 0 && temperature <= 1)) {
    throw new Error("温度要在 0 到 1 之间。恢复：把滑块拖回范围内再发。");
  }
  if (!(topP >= 0.01 && topP <= 1)) {
    throw new Error("top_p 要在 0.01 到 1 之间。恢复：把滑块拖回范围内再发。");
  }
  return { reasoning_effort: effort, temperature, top_p: topP };
}
