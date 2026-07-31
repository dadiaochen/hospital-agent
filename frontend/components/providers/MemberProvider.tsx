"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api } from "@/lib/api/client";
import type { FamilyMember } from "@/lib/api/types";
import { useApiResource } from "@/lib/useApiResource";

type MemberContextValue = {
  members: FamilyMember[];
  selectedMember: FamilyMember | null;
  selectedMemberId: string | null;
  setSelectedMemberId: (memberId: string) => void;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

const MemberContext = createContext<MemberContextValue | null>(null);

export function MemberProvider({ children }: { children: React.ReactNode }) {
  const membersResource = useApiResource("family-members", (signal) =>
    api.listFamilyMembers(signal),
  );
  const members = useMemo(
    () => membersResource.data ?? [],
    [membersResource.data],
  );
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);

  useEffect(() => {
    if (members.length === 0) {
      setSelectedMemberId(null);
      return;
    }
    if (!members.some((member) => member.id === selectedMemberId)) {
      setSelectedMemberId(members[0].id);
    }
  }, [members, selectedMemberId]);

  const selectedMember = useMemo(
    () => members.find((member) => member.id === selectedMemberId) ?? null,
    [members, selectedMemberId],
  );

  return (
    <MemberContext.Provider
      value={{
        members,
        selectedMember,
        selectedMemberId,
        setSelectedMemberId,
        loading: membersResource.loading,
        error: membersResource.error,
        reload: membersResource.reload,
      }}
    >
      {children}
    </MemberContext.Provider>
  );
}

export function useMember(): MemberContextValue {
  const context = useContext(MemberContext);
  if (!context) {
    throw new Error("useMember must be used inside MemberProvider");
  }
  return context;
}
