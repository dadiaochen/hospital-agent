"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { AgentRunResult } from "@/components/AgentRunResult";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { api } from "@/lib/api/client";
import type { AgentRunExecution } from "@/lib/api/types";
import { createIdempotencyKey } from "@/lib/idempotency";

const SCENARIOS = [
  { label: "正常续方", text: "我爸的降压药快吃完了，帮我看看能不能续方。", medicationName: "苯磺酸氨氯地平片", city: "上海" },
  { label: "复诊材料", text: "我妈上次开的中药快喝完了，帮我整理复诊材料。", medicationName: "中药颗粒", city: "上海" },
  { label: "用药提醒", text: "帮我给妈妈设置每天早晚的用药提醒。", medicationName: "二甲双胍", city: "上海" },
  { label: "高风险拦截", text: "我爸这个降压药能不能加量？", medicationName: "苯磺酸氨氯地平片", city: "上海" },
] as const;

export default function AgentPage() {
  const { selectedMemberId, selectedMember } = useMember();
  const [userInput, setUserInput] = useState("");
  const [medicationName, setMedicationName] = useState("");
  const [city, setCity] = useState("");
  const [execution, setExecution] = useState<AgentRunExecution | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const [confirmationMessage, setConfirmationMessage] = useState("我确认仅创建本地草稿，不执行外部提交。");
  const startKeyRef = useRef<string | null>(null);
  const confirmationKeyRef = useRef<string | null>(null);
  const activeMemberIdRef = useRef(selectedMemberId);

  useEffect(() => {
    activeMemberIdRef.current = selectedMemberId;
    setExecution(null);
    setError(null);
    setSubmitting(false);
    setConfirmationChecked(false);
    startKeyRef.current = null;
    confirmationKeyRef.current = null;
  }, [selectedMemberId]);

  function applyScenario(scenario: (typeof SCENARIOS)[number]) {
    setUserInput(scenario.text);
    setMedicationName(scenario.medicationName);
    setCity(scenario.city);
    setExecution(null);
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
        ...(medicationName.trim() ? { medication_name: medicationName.trim() } : {}),
        ...(city.trim() ? { city: city.trim() } : {}),
        human_confirmation_granted: false,
      });
      if (activeMemberIdRef.current !== requestMemberId) return;
      setExecution(result);
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

  async function confirmLocalDraft() {
    if (!execution || !selectedMemberId || !confirmationChecked || submitting) return;
    const requestMemberId = selectedMemberId;
    setSubmitting(true);
    setError(null);
    confirmationKeyRef.current ??= createIdempotencyKey("confirm");
    try {
      const result = await api.continueAgentRun(execution.run.id, requestMemberId, {
        idempotency_key: confirmationKeyRef.current,
        confirmation_message: confirmationMessage.trim(),
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
        description="输入慢病续方、复诊材料、用药提醒或高风险医疗问题。系统只整理信息、生成本地草稿并展示可审计来源，不替代医生诊断和处方。"
        eyebrow="MVP Demo"
        title="Agent 对话与安全确认"
      >
        {selectedMember ? <span className="text-sm font-semibold text-[#31534f]">当前成员：{selectedMember.name}</span> : null}
      </PageHeader>

      <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap gap-2">
          {SCENARIOS.map((scenario) => (
            <button className="rounded-full border border-[#bcd2cc] px-3 py-2 text-xs font-semibold text-[#31534f] hover:bg-[#edf7f3]" key={scenario.label} onClick={() => applyScenario(scenario)} type="button">
              {scenario.label}
            </button>
          ))}
        </div>

        <form className="mt-5 grid gap-4" onSubmit={submitRun}>
          <label className="grid gap-2 text-sm font-semibold text-[#31534f]">
            你的任务
            <textarea
              className="min-h-28 rounded-xl border border-[#cdded8] px-4 py-3 font-normal leading-6 outline-none focus:border-[#0f766e]"
              maxLength={4000}
              onChange={(event) => { setUserInput(event.target.value); startKeyRef.current = null; }}
              placeholder="例如：我爸的降压药快吃完了，帮我看看能不能续方。"
              required
              value={userInput}
            />
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            <TextInput label="药品名（可选）" onChange={(value) => { setMedicationName(value); startKeyRef.current = null; }} value={medicationName} />
            <TextInput label="城市（可选）" onChange={(value) => { setCity(value); startKeyRef.current = null; }} value={city} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs leading-5 text-[#71847f]">顶部选中的成员是唯一任务作用域。首次请求固定发送 human_confirmation_granted=false；需要确认时由后端返回待确认状态。</p>
            <button className="rounded-xl bg-[#0f766e] px-5 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-[#94a3b8]" disabled={!selectedMemberId || !userInput.trim() || submitting} type="submit">
              {submitting ? "运行中..." : "运行 Agent"}
            </button>
          </div>
        </form>
      </section>

      {error ? <section className="rounded-2xl border border-[#fecaca] bg-[#fff8f7] p-5 text-sm text-[#9f1d18]" role="alert">{error}</section> : null}

      {execution ? (
        <AgentRunResult execution={execution}>
          {canConfirm ? (
            <div className="rounded-xl border border-[#f2d58a] bg-[#fffbeb] p-4">
              <h3 className="font-bold text-[#713f12]">待人工确认的本地动作</h3>
              <label className="mt-3 grid gap-2 text-sm text-[#785a2f]">
                确认说明
                <textarea className="min-h-20 rounded-lg border border-[#e9cf8a] bg-white px-3 py-2 text-[#334155]" maxLength={1000} onChange={(event) => { setConfirmationMessage(event.target.value); confirmationKeyRef.current = null; }} value={confirmationMessage} />
              </label>
              <label className="mt-3 flex items-start gap-2 text-sm leading-6 text-[#785a2f]">
                <input checked={confirmationChecked} className="mt-1" onChange={(event) => setConfirmationChecked(event.target.checked)} type="checkbox" />
                我理解本次确认只会创建或更新本地草稿，不代表医生同意，也不会提交购药、复诊或提醒到外部系统。
              </label>
              <button className="mt-4 rounded-lg bg-[#92400e] px-4 py-2 text-sm font-bold text-white disabled:bg-[#cbd5e1]" disabled={!confirmationChecked || !confirmationMessage.trim() || submitting} onClick={confirmLocalDraft} type="button">
                {submitting ? "确认续跑中..." : "确认并创建本地草稿"}
              </button>
            </div>
          ) : null}
        </AgentRunResult>
      ) : null}
    </div>
  );
}

function TextInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-2 text-sm font-semibold text-[#31534f]">
      {label}
      <input className="rounded-xl border border-[#cdded8] px-4 py-3 font-normal outline-none focus:border-[#0f766e]" onChange={(event) => onChange(event.target.value)} value={value} />
    </label>
  );
}
