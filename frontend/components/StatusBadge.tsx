type StatusBadgeProps = {
  children: React.ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
};

const toneClasses = {
  neutral: "bg-[#eef3f2] text-[#45615d]",
  success: "bg-[#dcfce7] text-[#166534]",
  warning: "bg-[#fff3cd] text-[#92400e]",
  danger: "bg-[#fee2e2] text-[#991b1b]",
};

export function StatusBadge({ children, tone = "neutral" }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}
