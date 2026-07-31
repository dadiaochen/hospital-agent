type AsyncContentProps = {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  onRetry?: () => void;
  children: React.ReactNode;
};

export function AsyncContent({
  loading,
  error,
  empty,
  emptyTitle = "暂无数据",
  emptyDescription = "当前成员还没有可展示的记录。",
  onRetry,
  children,
}: AsyncContentProps) {
  if (loading) {
    return (
      <div aria-live="polite" className="grid gap-3" role="status">
        {[0, 1, 2].map((index) => (
          <div
            className="h-28 animate-pulse rounded-2xl border border-[#e1ebe7] bg-white"
            key={index}
          />
        ))}
        <span className="sr-only">数据加载中</span>
      </div>
    );
  }

  if (error) {
    return (
      <section
        className="rounded-2xl border border-[#fecaca] bg-[#fff8f7] p-6"
        role="alert"
      >
        <p className="font-semibold text-[#9f1d18]">数据暂时无法加载</p>
        <p className="mt-2 text-sm leading-6 text-[#7f1d1d]">{error}</p>
        {onRetry ? (
          <button
            className="mt-4 rounded-lg bg-[#9f1d18] px-4 py-2 text-sm font-semibold text-white"
            onClick={onRetry}
            type="button"
          >
            重新加载
          </button>
        ) : null}
      </section>
    );
  }

  if (empty) {
    return (
      <section className="rounded-2xl border border-dashed border-[#cdded8] bg-white p-8 text-center">
        <p className="font-semibold text-[#31534f]">{emptyTitle}</p>
        <p className="mt-2 text-sm text-[#64748b]">{emptyDescription}</p>
      </section>
    );
  }

  return <>{children}</>;
}
