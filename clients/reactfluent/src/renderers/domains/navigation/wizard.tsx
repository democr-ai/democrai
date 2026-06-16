import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { DefaultButton, PrimaryButton } from '@fluentui/react';

export const Wizard: React.FC<any> = ({
  id,
  steps = [],
  active_step_id,
  validated_steps = [],
  action,
  params,
  allow_step_click = true,
  show_controls = true,
  prev_label = 'Previous',
  next_label = 'Next',
  style,
  onAction,
}) => {
  const wizardId = String(id || '').trim();
  const allSteps = Array.isArray(steps) ? steps : [];
  const validatedSteps = Array.isArray(validated_steps) ? validated_steps : [];
  const fallbackId = String(allSteps[0]?.id || '');
  const requestedActiveId = String(active_step_id || fallbackId || '');
  const activeId = allSteps.some((entry: any) => String(entry?.id) === requestedActiveId)
    ? requestedActiveId
    : fallbackId;
  const actionParams = params && typeof params === 'object' && !Array.isArray(params) ? params : {};
  const baseWizardCtx = {
    ...actionParams,
    ...(wizardId
      ? {
          wizard_id: actionParams.wizard_id ?? wizardId,
          target_wizard: actionParams.target_wizard ?? wizardId,
        }
      : {}),
    steps: allSteps,
    active_step_id: activeId,
    validated_steps: validatedSteps,
  };
  const activeIndex = Math.max(0, allSteps.findIndex((entry: any) => String(entry?.id) === activeId));
  const active = allSteps[activeIndex];
  const canGoNext = activeIndex < allSteps.length - 1;

  if (!allSteps.length) {
    return (
      <section style={parseStyle(style)} className="ds-wizard">
        <div className="ds-wizard-empty">No steps configured.</div>
      </section>
    );
  }

  return (
    <section style={parseStyle(style)} className="ds-wizard">
      <header className="ds-wizard-header">
        <div className="ds-wizard-steps">
          {allSteps.map((step: any, idx: number) => {
            const stepId = String(step?.id || `step_${idx + 1}`);
            const isActive = stepId === activeId;
            const isValidated = validatedSteps.map((entry: any) => String(entry)).includes(stepId);
            const canClickStep = Boolean(allow_step_click);
            return (
              <button
                key={stepId}
                type="button"
                className={`ds-wizard-step ${isActive ? 'ds-wizard-step-active' : ''} ${isValidated ? 'ds-wizard-step-done' : ''}`}
                disabled={!canClickStep}
                onClick={() =>
                  emitActionSpec(action, onAction, {
                    ...baseWizardCtx,
                    intent: 'step_click',
                    step_id: stepId,
                    step_index: idx,
                  })
                }
              >
                <span className="ds-wizard-step-index">{isValidated && !isActive ? <i className="ri-check-line" /> : idx + 1}</span>
                <span className="ds-wizard-step-label">{getLiteral(step?.title || stepId)}</span>
              </button>
            );
          })}
        </div>
      </header>
      <div className="ds-wizard-body">
        <div className="ds-wizard-heading">
          <h3 className="ds-wizard-title">{getLiteral(active?.title || activeId)}</h3>
          <span className="ds-wizard-badge">Step {activeIndex + 1}/{allSteps.length}</span>
        </div>
        {active?.description ? <p className="ds-wizard-description">{getLiteral(active.description)}</p> : null}
        {active?.content ? <p className="ds-wizard-content">{getLiteral(active.content)}</p> : null}
        {show_controls ? (
          <div className="ds-wizard-controls">
            <DefaultButton
              type="button"
              className="ds-button ds-button-small ds-wizard-back"
              disabled={activeIndex <= 0}
              onClick={() =>
                emitActionSpec(action, onAction, {
                  ...baseWizardCtx,
                  intent: 'prev',
                  step_id: activeId,
                  step_index: activeIndex,
                })
              }
            >
              <span className="ds-wizard-nav-icon ds-wizard-nav-icon-left" aria-hidden="true" />
              <span>{getLiteral(prev_label)}</span>
            </DefaultButton>
            <PrimaryButton
              type="button"
              className="ds-button ds-button-small ds-wizard-next"
              disabled={!canGoNext}
              onClick={() =>
                emitActionSpec(action, onAction, {
                  ...baseWizardCtx,
                  intent: 'next',
                  step_id: activeId,
                  step_index: activeIndex,
                })
              }
            >
              <span>{getLiteral(next_label)}</span>
              <span className="ds-wizard-nav-icon ds-wizard-nav-icon-right" aria-hidden="true" />
            </PrimaryButton>
          </div>
        ) : null}
      </div>
    </section>
  );
};
