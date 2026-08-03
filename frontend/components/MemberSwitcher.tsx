"use client";

import { useMember } from "@/components/providers/MemberProvider";

const relationshipLabels: Record<string, string> = {
  self: "本人",
  father: "父亲",
  mother: "母亲",
  spouse: "配偶",
  child: "子女",
};

function getMemberLabel(relationship: string, name: string) {
  const relationshipLabel = relationshipLabels[relationship] ?? "家庭成员";
  return `${relationshipLabel} · ${name}`;
}

export function MemberSwitcher() {
  const {
    members,
    selectedMemberId,
    setSelectedMemberId,
    loading,
    error,
    reload,
  } = useMember();

  if (loading) {
    return (
      <div
        aria-label="正在加载家庭成员"
        className="h-10 w-40 animate-pulse rounded-full bg-[#e7efec] sm:w-52"
        role="status"
      />
    );
  }

  if (error) {
    return (
      <button
        aria-label="重新加载家庭成员"
        className="inline-flex min-h-10 items-center rounded-full border border-[#fecaca] bg-[#fff7f7] px-3 text-sm font-medium text-[#b42318] transition-colors hover:border-[#fca5a5] hover:bg-[#fff1f1] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#b42318]/20"
        onClick={reload}
        type="button"
      >
        成员加载失败，点击重试
      </button>
    );
  }

  if (members.length === 0) {
    return (
      <div className="inline-flex min-h-10 items-center rounded-full border border-[#d7e5e0] bg-white px-3 text-sm text-[#64748b]">
        暂无家庭成员
      </div>
    );
  }

  const selectedMember = members.find(
    (member) => member.id === selectedMemberId,
  );

  return (
    <label className="group relative inline-flex min-w-0 items-center gap-2 rounded-full border border-[#d7e5e0] bg-white/95 px-2 py-1.5 text-sm shadow-[0_4px_14px_rgba(23,60,56,0.06)] transition-colors hover:border-[#0f766e] focus-within:border-[#0f766e] focus-within:ring-2 focus-within:ring-[#0f766e]/15">
      <span
        aria-hidden="true"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#e7f4f0] text-xs font-semibold text-[#0f766e]"
      >
        {selectedMember?.name?.slice(0, 1) ?? "家"}
      </span>
      <span className="sr-only">当前家庭成员</span>
      <span className="relative min-w-0">
        <select
          aria-label="当前家庭成员"
          className="max-w-[9rem] appearance-none bg-transparent py-1 pl-0 pr-5 font-semibold leading-5 text-[#173c38] outline-none sm:max-w-[13rem]"
          onChange={(event) => setSelectedMemberId(event.target.value)}
          value={selectedMemberId ?? ""}
        >
          {members.map((member) => (
            <option key={member.id} value={member.id}>
              {getMemberLabel(member.relationship, member.name)}
            </option>
          ))}
        </select>
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute right-0 top-1/2 h-4 w-4 -translate-y-1/2 text-[#64748b]"
          fill="none"
          viewBox="0 0 24 24"
        >
          <path
            d="m7 10 5 5 5-5"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.8"
          />
        </svg>
      </span>
    </label>
  );
}
