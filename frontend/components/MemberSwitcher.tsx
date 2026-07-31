"use client";

import { useMember } from "@/components/providers/MemberProvider";

const relationshipLabels: Record<string, string> = {
  self: "本人",
  father: "父亲",
  mother: "母亲",
};

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
    return <div className="h-10 w-52 animate-pulse rounded-lg bg-[#e7efec]" />;
  }

  if (error) {
    return (
      <button
        className="rounded-lg border border-[#fecaca] bg-[#fff7f7] px-3 py-2 text-sm font-medium text-[#b42318]"
        onClick={reload}
        type="button"
      >
        成员加载失败，点击重试
      </button>
    );
  }

  if (members.length === 0) {
    return (
      <div className="rounded-lg border border-[#d7e5e0] bg-white px-3 py-2 text-sm text-[#64748b]">
        暂无家庭成员
      </div>
    );
  }

  return (
    <label className="flex items-center gap-3 rounded-lg border border-[#d7e5e0] bg-white px-3 py-2 text-sm shadow-sm">
      <span className="whitespace-nowrap text-[#64748b]">当前成员</span>
      <select
        aria-label="当前家庭成员"
        className="min-w-28 bg-transparent font-semibold text-[#173c38] outline-none"
        onChange={(event) => setSelectedMemberId(event.target.value)}
        value={selectedMemberId ?? ""}
      >
        {members.map((member) => (
          <option key={member.id} value={member.id}>
            {relationshipLabels[member.relationship] ?? member.relationship} · {member.name}
          </option>
        ))}
      </select>
    </label>
  );
}
