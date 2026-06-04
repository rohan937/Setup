import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  WALKTHROUGH_STEPS,
  findDemoStrategyId,
  hasDemoStrategies,
  loadWalkthroughState,
  saveWalkthroughState,
  type WalkthroughStep,
} from "@/lib/demoWalkthrough";
import type { Strategy } from "@/types";

interface DemoWalkthroughProps {
  strategies: Strategy[];
  onClose: () => void;
  startStep?: number;
}

const TOTAL = WALKTHROUGH_STEPS.length;

function clampIndex(stepNumber: number): number {
  const idx = stepNumber - 1;
  if (idx < 0) return 0;
  if (idx > TOTAL - 1) return TOTAL - 1;
  return idx;
}

export default function DemoWalkthrough({
  strategies,
  onClose,
  startStep,
}: DemoWalkthroughProps) {
  const navigate = useNavigate();

  const [index, setIndex] = useState<number>(() => {
    const initial =
      startStep !== undefined ? startStep : loadWalkthroughState().lastStep;
    return clampIndex(initial);
  });

  const step: WalkthroughStep = WALKTHROUGH_STEPS[index];
  const stepNumber = step.step;
  const isFirst = index === 0;
  const isLast = index === TOTAL - 1;

  function goToIndex(nextIndex: number) {
    const clamped = clampIndex(nextIndex + 1);
    setIndex(clamped);
    saveWalkthroughState({
      dismissed: false,
      completed: false,
      lastStep: WALKTHROUGH_STEPS[clamped].step,
    });
  }

  function handleExit() {
    saveWalkthroughState({
      dismissed: true,
      completed: false,
      lastStep: stepNumber,
    });
    onClose();
  }

  function handleFinish() {
    saveWalkthroughState({
      dismissed: true,
      completed: true,
      lastStep: TOTAL,
    });
    onClose();
  }

  function handleNext() {
    if (isLast) {
      handleFinish();
    } else {
      goToIndex(index + 1);
    }
  }

  function handlePrevious() {
    if (!isFirst) goToIndex(index - 1);
  }

  function handleGo() {
    if (step.target.kind === "route") {
      navigate(step.target.path);
      return;
    }
    const id = findDemoStrategyId(strategies, step.target.nameKey);
    if (id) navigate(`/strategies/${id}`);
  }

  const strategyMissing =
    step.target.kind === "strategy" &&
    (!hasDemoStrategies(strategies) ||
      findDemoStrategyId(strategies, step.target.nameKey) === null);

  return (
    <div className="fixed bottom-4 right-4 z-40 w-[22rem] max-w-[calc(100vw-2rem)] rounded-card border border-border bg-bg-800 shadow-panel">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="caption">Guided demo</span>
        <div className="flex items-center gap-2">
          <span className="text-2xs text-text-muted">
            Step {stepNumber} of {TOTAL}
          </span>
          <button
            type="button"
            onClick={handleExit}
            aria-label="Close walkthrough"
            className="rounded-control border border-border px-1.5 py-0.5 text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="space-y-3 px-4 py-3">
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-text-primary">{step.title}</h3>
          <p className="text-xs leading-relaxed text-text-secondary">
            {step.explanation}
          </p>
        </div>

        <div className="space-y-1">
          <span className="caption">What to look for</span>
          <ul className="space-y-1">
            {step.lookFor.map((item, i) => (
              <li
                key={i}
                className="flex gap-1.5 text-2xs text-text-secondary"
              >
                <span aria-hidden="true">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {strategyMissing ? (
          <div className="space-y-2 rounded-card border border-fidelity-medium/40 bg-fidelity-medium/10 px-3 py-2">
            <p className="text-xs text-fidelity-medium">
              Run Clean Realistic Demo first.
            </p>
            <Link
              to="/admin/demo-controls"
              className="inline-block rounded-control border border-fidelity-medium/40 bg-fidelity-medium/15 px-2.5 py-1 text-2xs text-fidelity-medium hover:bg-fidelity-medium/25"
            >
              Open Demo Controls
            </Link>
          </div>
        ) : (
          <button
            type="button"
            onClick={handleGo}
            className="rounded-control border border-accent-500/40 bg-accent-500/15 px-3 py-1.5 text-sm text-accent-200 hover:bg-accent-500/25"
          >
            {step.goLabel}
          </button>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-border px-4 py-3">
        <button
          type="button"
          onClick={handlePrevious}
          disabled={isFirst}
          className="rounded-control border border-border px-2.5 py-1 text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-text-secondary"
        >
          Previous
        </button>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleExit}
            className="rounded-control border border-border px-2.5 py-1 text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            Exit
          </button>
          <button
            type="button"
            onClick={handleNext}
            className="rounded-control border border-border px-2.5 py-1 text-2xs text-text-secondary hover:bg-bg-600 hover:text-text-primary"
          >
            {isLast ? "Finish" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
