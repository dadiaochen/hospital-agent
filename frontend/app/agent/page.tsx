"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { AgentRunResult } from "@/components/AgentRunResult";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { api } from "@/lib/api/client";
import type { AgentRunExecution } from "@/lib/api/types";
import { createIdempotencyKey } from "@/lib/idempotency";

const QUICK_PROMPTS = [
  { label: "用药与续方", text: "家人的药快吃完了，帮我整理续方需要准备的信息。" },
  { label: "复诊准备", text: "帮我整理下一次复诊前需要准备的资料。" },
  { label: "报告解读", text: "我有一份检查报告，想先了解需要关注哪些信息。" },
  { label: "健康记录", text: "帮我把最近的家庭健康情况整理成一份记录。" },
] as const;

const CONFIRMATION_MESSAGE = "用户已阅读上面的整理内容并确认继续。";

export default function AgentPage() {
  const { selectedMemberId, selectedMember } = useMember();
  const [userInput, setUserInput] = useState("");
  const [submittedInput, setSubmittedInput] = useState("");
  const [execution, setExecution] = useState<AgentRunExecution | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const startKeyRef = useRef<string | null>(null);
  const confirmationKeyRef = useRef<string | null>(null);
  const activeMemberIdRef = useRef(selectedMemberId);

  useEffect(() => {
    activeMemberIdRef.current = selectedMemberId;
    setExecution(null);
    setSubmittedInput("");
    setError(null);
    setSubmitting(false);
    setConfirmationChecked(false);
    startKeyRef.current = null;
    confirmationKeyRef.current = null;
  }, [selectedMemberId]);

  function applyQuickPrompt(prompt: string) {
    setUserInput(prompt);
    setExecution(null);
    setSubmittedInput("");
    setError(null);
    startKeyRef.current = null;
  }

  async function submitRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedMemberId || !userInput.trim() || submitting) return;
    const requestMemberId = selectedMemberId;
    setSubmitting(true);
    setError(null);
    startKeyRef.current ??= createIdempotencyKey("run");
    try {
      const result = await api.createAgentRun({
        member_id: requestMemberId,
        idempotency_key: startKeyRef.current,
        user_input: userInput.trim(),
        human_confirmation_granted: false,
      });
      if (activeMemberIdRef.current !== requestMemberId) return;
      setExecution(result);
      setSubmittedInput(userInput.trim());
      setConfirmationChecked(false);
      startKeyRef.current = null;
      confirmationKeyRef.current = null;
    } catch (requestError) {
      if (activeMemberIdRef.current !== requestMemberId) return;
      setError(requestError instanceof Error ? requestError.message : "Agent 运行失败，请稍后重试");
    } finally {
      if (activeMemberIdRef.current === requestMemberId) setSubmitting(false);
    }
  }

  async function confirmNextStep() {
    if (!execution || !selectedMemberId || !confirmationChecked || submitting) return;
    const requestMemberId = selectedMemberId;
    setSubmitting(true);
    setError(null);
    confirmationKeyRef.current ??= createIdempotencyKey("confirm");
    try {
      const result = await api.continueAgentRun(execution.run.id, requestMemberId, {
        idempotency_key: confirmationKeyRef.current,
        confirmation_message: CONFIRMATION_MESSAGE,
        human_confirmation_granted: true,
      });
      if (activeMemberIdRef.current !== requestMemberId) return;
      setExecution(result);
      setConfirmationChecked(false);
      confirmationKeyRef.current = null;
    } catch (requestError) {
      if (activeMemberIdRef.current !== requestMemberId) return;
      setError(requestError instanceof Error ? requestError.message : "确认续跑失败，请稍后重试");
    } finally {
      if (activeMemberIdRef.current === requestMemberId) setSubmitting(false);
    }
  }

  const canConfirm = execution !== null && execution.run.status === "needs_confirmation" &&
    execution.artifacts.run_trace.final_answer.waiting_for_user_confirmation && !execution.artifacts.safety_trace.blocked;

  return (
    <div className="grid gap-5">
      <PageHeader
        description="描述症状、用药、复诊或报告问题，我会先帮你把信息整理清楚。"
        eyebrow="AI 健康助手"
        title="今天想先处理什么？"
      >
        {selectedMember ? <span className="rounded-full bg-[#e2f3ef] px-3 py-1.5 text-sm font-semibold text-[#0f766e]">正在为：{selectedMember.name}</span> : null}
      </PageHeader>

      <section className="mx-auto flex w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-[#d9e8e2] bg-white shadow-[0_16px_45px_rgba(21,69,62,0.07)]">
        <div className="flex min-h-[360px] flex-col items-center justify-center px-6 py-14 text-center sm:px-12">
          <div aria-hidden="true" className="grid h-16 w-16 place-items-center rounded-[22px] bg-[#e2f3ef] text-xl font-black text-[#0f766e]">问</div>
          <h2 className="mt-6 text-2xl font-black tracking-tight text-[#173c38] sm:text-3xl">你好，想从哪件事开始？</h2>
          <p className="mt-3 max-w-xl text-sm leading-7 text-[#637a74] sm:text-base">
            把你关心的家庭健康问题直接告诉我，我会帮你理清信息和需要准备的内容。
          </p>
          <div className="mt-7 flex flex-wrap justify-center gap-2 text-sm text-[#4d7169]">
            {QUICK_PROMPTS.map((prompt) => (
              <button
                className="rounded-full bg-[#f0f8f5] px-3 py-1.5 transition hover:bg-[#dff3ed] disabled:cursor-not-allowed disabled:opacity-60"
                disabled={!selectedMemberId || submitting}
                key={prompt.label}
                onClick={() => applyQuickPrompt(prompt.text)}
                type="button"
              >
                {prompt.label}
              </button>
            ))}
          </div>
        </div>

        <div className="border-t border-[#e4efeb] bg-[#fbfefd] p-4 sm:p-5">
          <form className="grid gap-3" onSubmit={submitRun}>
            <label className="grid gap-2 text-sm font-semibold text-[#31534f]">
              <span>输入你的问题</span>
              <textarea
                aria-label="输入你的问题"
                className="min-h-32 resize-y rounded-2xl border border-[#cdded8] bg-white px-4 py-3 font-normal leading-6 outline-none transition placeholder:text-[#9aada7] focus:border-[#0f766e] focus:ring-4 focus:ring-[#dff3ee] disabled:cursor-not-allowed disabled:bg-[#f3f7f5]"
                disabled={!selectedMemberId || submitting}
                maxLength={4000}
                onChange={(event) => { setUserInput(event.target.value); startKeyRef.current = null; }}
                placeholder="例如：帮我整理妈妈的复诊材料"
                required
                value={userInput}
              />
            </label>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-5 text-[#71847f]">正在为 {selectedMember?.name ?? "家庭成员"} 提供帮助</p>
              <button className="w-full rounded-xl bg-[#173c38] px-5 py-3 text-sm font-bold text-white transition hover:bg-[#0f766e] disabled:cursor-not-allowed disabled:bg-[#a8bcb7] sm:w-auto" disabled={!selectedMemberId || !userInput.trim() || submitting} type="submit">
                {submitting ? "正在整理..." : "开始咨询"}
              </button>
            </div>
          </form>
        </div>
      </section>

      {error ? <section className="rounded-2xl border border-[#fecaca] bg-[#fff8f7] p-5 text-sm text-[#9f1d18]" role="alert">{error}</section> : null}

      {execution ? (
        <div aria-label="本次咨询" className="grid gap-3">
          {submittedInput ? (
            <div className="ml-auto max-w-3xl rounded-2xl rounded-br-md bg-[#173c38] px-4 py-3 text-sm leading-6 text-white shadow-sm">
              {submittedInput}
            </div>
          ) : null}
          <AgentRunResult execution={execution}>
            {canConfirm ? (
              <div className="rounded-2xl border border-[#f2d58a] bg-[#fffbeb] p-5">
                <p className="text-xs font-black uppercase tracking-[0.14em] text-[#b26c09]">下一步</p>
                <h3 className="mt-1 font-black text-[#713f12]">请确认是否继续</h3>
                <p className="mt-3 text-sm leading-6 text-[#785a2f]">
                  我已经把这次咨询的重点整理在上面。请先确认内容无误，再继续完成后续准备；如果需要调整，可以回到上方修改问题。
                </p>
                <label className="mt-4 flex items-start gap-2 text-sm leading-6 text-[#785a2f]">
                  <input
                    aria-label="确认继续"
                    checked={confirmationChecked}
                    className="mt-1"
                    onChange={(event) => setConfirmationChecked(event.target.checked)}
                    type="checkbox"
                  />
                  <span>我已阅读上面的整理内容，确认继续。</span>
                </label>
                <button
                  className="mt-4 rounded-xl bg-[#92400e] px-4 py-2.5 text-sm font-bold text-white disabled:bg-[#cbd5e1]"
                  disabled={!confirmationChecked || submitting}
                  onClick={confirmNextStep}
                  type="button"
                >
                  {submitting ? "正在继续..." : "确认并继续"}
                </button>
              </div>
            ) : null}
          </AgentRunResult>
        </div>
      ) : null}
    </div>
  );
}
