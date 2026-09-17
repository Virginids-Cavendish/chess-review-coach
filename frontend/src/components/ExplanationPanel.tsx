"use client";

import type { MomentExplanation } from "@/lib/types";
import { formatPercent } from "@/lib/labels";

interface ExplanationPanelProps {
  explanation: MomentExplanation | null;
  loading: boolean;
  error: string | null;
  llmConfigured: boolean;
  onRetry: () => void;
}

function Section({ title, body }: { title: string; body: string }) {
  if (!body) return null;
  return (
    <div className="py-1.5">
      <div className="text-xs font-medium" style={{ color: "var(--muted)" }}>
        {title}
      </div>
      <p className="mt-0.5 whitespace-pre-wrap text-sm leading-relaxed">{body}</p>
    </div>
  );
}

/**
 * AI COACH EXPLANATION — visually and structurally separate from engine evidence.
 *
 * The badge always states where the text came from (LLM or the deterministic template
 * fallback), and validation warnings are surfaced instead of hidden.
 */
export default function ExplanationPanel({
  explanation,
  loading,
  error,
  llmConfigured,
  onRetry,
}: ExplanationPanelProps) {
  if (loading) {
    return (
      <div className="coach-block rounded-r-md p-3 text-sm" style={{ color: "var(--muted)" }}>
        正在生成解释…
      </div>
    );
  }

  if (error) {
    return (
      <div className="coach-block rounded-r-md p-3 text-sm">
        <div className="mb-1 flex items-center gap-2">
          <span className="tag tag-coach">AI 解释暂不可用</span>
        </div>
        <p style={{ color: "var(--muted)" }}>{error}</p>
        <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
          引擎复盘不受影响，可以在上面查看 Stockfish 证据。
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 rounded border px-2 py-1 text-xs"
          style={{ borderColor: "var(--border)" }}
        >
          重新生成
        </button>
      </div>
    );
  }

  if (!explanation) return null;
  const { explanation: text, source } = explanation;

  return (
    <div className="coach-block rounded-r-md p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="tag tag-coach">
          {source === "llm" ? "AI 教练解释" : "规则模板说明（未使用 AI）"}
        </span>
        <span className="text-xs" style={{ color: "var(--muted)" }}>
          置信度 {formatPercent(text.confidence)}
          {explanation.model ? ` · ${explanation.model}` : ""}
          {explanation.cached ? " · 已缓存" : ""}
        </span>
      </div>

      <p className="mb-2 text-sm leading-relaxed">{text.summary}</p>

      <Section title="发生了什么" body={text.what_happened} />
      <Section title="为什么重要" body={text.why_it_matters} />
      <Section title="可能的人类失误" body={text.likely_human_error} />
      <Section title="下次应该这样想" body={text.better_thinking_process} />
      <Section title="可以复用的经验" body={text.general_lesson} />
      <Section title="为什么引擎推荐那一手" body={text.best_move_explanation} />

      {text.concept_tags.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {text.concept_tags.map((tag) => (
            <span key={tag} className="tag tag-coach">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {explanation.validation_warnings.length > 0 ? (
        <ul className="mt-2 space-y-1 text-xs text-amber-300">
          {explanation.validation_warnings.map((warning) => (
            <li key={warning}>· {warning}</li>
          ))}
        </ul>
      ) : null}

      {source === "rules" && llmConfigured ? (
        <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
          已配置 DeepSeek，但这次没有拿到合格的 AI 输出，因此显示规则模板说明。
        </p>
      ) : null}

      {source === "rules" && !llmConfigured ? (
        <p className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
          未配置 DEEPSEEK_API_KEY：当前只显示基于引擎证据的规则模板说明。
        </p>
      ) : null}
    </div>
  );
}
