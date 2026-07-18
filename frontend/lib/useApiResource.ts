"use client";

import { useEffect, useRef, useState } from "react";

type ResourceState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

export function useApiResource<T>(
  resourceKey: string | null,
  loader: (signal: AbortSignal) => Promise<T>,
) {
  const loaderRef = useRef(loader);
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<ResourceState<T>>({
    data: null,
    error: null,
    loading: resourceKey !== null,
  });

  loaderRef.current = loader;

  useEffect(() => {
    if (resourceKey === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }

    const controller = new AbortController();
    setState({ data: null, error: null, loading: true });

    loaderRef.current(controller.signal).then(
      (data) => setState({ data, error: null, loading: false }),
      (error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          data: null,
          error: error instanceof Error ? error.message : "请求失败，请稍后重试",
          loading: false,
        });
      },
    );

    return () => controller.abort();
  }, [resourceKey, reloadToken]);

  return {
    ...state,
    reload: () => setReloadToken((current) => current + 1),
  };
}
