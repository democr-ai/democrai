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
      <section style={parseStyle(style)} className="a2ui-wizard">
        <div className="a2ui-wizard-empty">No steps configured.</div>
      </section>
    );
  }

  return (
    <section style={parseStyle(style)} className="a2ui-wizard">
      <header className="a2ui-wizard-header">
        <div className="a2ui-wizard-steps">
          {allSteps.map((step: any, idx: number) => {
            const stepId = String(step?.id || `step_${idx + 1}`);
            const isActive = stepId === activeId;
            const isValidated = validatedSteps.map((entry: any) => String(entry)).includes(stepId);
            const canClickStep = Boolean(allow_step_click);
            return (
              <button
                key={stepId}
                type="button"
                className={`a2ui-wizard-step ${isActive ? 'a2ui-wizard-step-active' : ''} ${isValidated ? 'a2ui-wizard-step-done' : ''}`}
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
                <span className="a2ui-wizard-step-index">{isValidated && !isActive ? <i className="ri-check-line" /> : idx + 1}</span>
                <span className="a2ui-wizard-step-label">{getLiteral(step?.title || stepId)}</span>
              </button>
            );
          })}
        </div>
      </header>
      <div className="a2ui-wizard-body">
        <div className="a2ui-wizard-heading">
          <h3 className="a2ui-wizard-title">{getLiteral(active?.title || activeId)}</h3>
          <span className="a2ui-wizard-badge">Step {activeIndex + 1}/{allSteps.length}</span>
        </div>
        {active?.description ? <p className="a2ui-wizard-description">{getLiteral(active.description)}</p> : null}
        {active?.content ? <p className="a2ui-wizard-content">{getLiteral(active.content)}</p> : null}
        {show_controls ? (
          <div className="a2ui-wizard-controls">
            <DefaultButton
              type="button"
              className="a2ui-button a2ui-button-small a2ui-wizard-back"
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
              <span className="a2ui-wizard-nav-icon a2ui-wizard-nav-icon-left" aria-hidden="true" />
              <span>{getLiteral(prev_label)}</span>
            </DefaultButton>
            <PrimaryButton
              type="button"
              className="a2ui-button a2ui-button-small a2ui-wizard-next"
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
              <span className="a2ui-wizard-nav-icon a2ui-wizard-nav-icon-right" aria-hidden="true" />
            </PrimaryButton>
          </div>
        ) : null}
      </div>
    </section>
  );
};
