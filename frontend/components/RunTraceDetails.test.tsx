import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RunTraceDetails } from "@/components/RunTraceDetails";
import { makeAgentExecution, makeToolCall } from "@/lib/agentTestFixtures";

afterEach(cleanup);

describe("RunTraceDetails", () => {
  it("shows role, tool, latency, error, fallback and evaluation fields", () => {
    const execution = makeAgentExecution({ status: "completed" });
    const toolCall = makeToolCall(execution.run.id);

    render(
      <RunTraceDetails
        artifacts={execution.artifacts}
        run={execution.run}
        toolCalls={[toolCall]}
      />,
    );

    expect(screen.getByText("RefillAgent")).toBeTruthy();
    expect(screen.getByText("query_medicine_box")).toBeTruthy();
    expect(screen.getByText("18 ms")).toBeTruthy();
    expect(screen.getByText("错误类型：timeout")).toBeTruthy();
    expect(screen.getByText("Fallback：use_cached_summary")).toBeTruthy();
    expect(screen.getByText("EvaluationResult")).toBeTruthy();
    expect(screen.getByText("Context isolation")).toBeTruthy();
    expect(screen.getByText(/Evaluator 不会修改最终答案或业务状态/)).toBeTruthy();
  });
});
