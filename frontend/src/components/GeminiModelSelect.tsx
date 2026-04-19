import { useQuery } from "@tanstack/react-query";
import { listGeminiChatModels } from "../api";
import { DEFAULT_GEMINI_MODEL, GeminiChatModel } from "../types";

type Props = {
  token: string | null;
  value: string;
  onChange: (modelId: string) => void;
  disabled?: boolean;
};

export function GeminiModelSelect({
  token,
  value,
  onChange,
  disabled,
}: Props) {
  const effectiveNoToken = (value.trim() || DEFAULT_GEMINI_MODEL);
  if (!token) {
    return (
      <div>
        <select className="input" value={effectiveNoToken} disabled>
          <option value={effectiveNoToken}>{effectiveNoToken}</option>
        </select>
      </div>
    );
  }

  const q = useQuery({
    queryKey: ["geminiChatModels"],
    queryFn: () => listGeminiChatModels(token!),
    enabled: !!token,
    staleTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const models = q.data ?? [];
  const byName = new Map(models.map((m) => [m.name, m]));
  const effective = value.trim() || DEFAULT_GEMINI_MODEL;
  const showUnknownFallback =
    !!effective &&
    !q.isLoading &&
    (q.isSuccess || q.isError) &&
    !byName.has(effective);
  const selectedMeta: GeminiChatModel | undefined = byName.get(effective);

  return (
    <div>
      <select
        className="input"
        value={effective}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || (!!token && q.isLoading)}
        aria-busy={q.isLoading}
      >
        {q.isLoading && (
          <option value={effective}>Загрузка списка моделей…</option>
        )}
        {!q.isLoading && showUnknownFallback && (
          <option value={effective}>
            {effective} (текущая, нет в списке API)
          </option>
        )}
        {!q.isLoading &&
          models.map((m) => (
            <option key={m.name} value={m.name}>
              {m.display_name?.trim() || m.name}
            </option>
          ))}
      </select>
      {q.isError && (
        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          Не удалось загрузить список моделей: выберите значение выше или
          обновите страницу.
        </div>
      )}
      {selectedMeta?.description && (
        <div
          className="muted"
          style={{
            fontSize: 11,
            marginTop: 6,
            lineHeight: 1.35,
            maxHeight: "2.7em",
            overflow: "hidden",
          }}
          title={selectedMeta.description}
        >
          {selectedMeta.description}
        </div>
      )}
    </div>
  );
}
