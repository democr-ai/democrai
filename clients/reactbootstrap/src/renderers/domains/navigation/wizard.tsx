import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Button, Card, CardBody, CardHeader, CardTitle, Badge } from 'design-react-kit';

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
      <Card style={parseStyle(style)} className="a2ui-wizard border">
        <CardBody className="p-4 text-center text-muted small">No steps configured.</CardBody>
      </Card>
    );
  }

  return (
    <Card style={parseStyle(style)} className="a2ui-wizard border">
      <CardHeader className="a2ui-wizard-header border-bottom p-3">
        <div className="a2ui-wizard-steps">
          {allSteps.map((step: any, idx: number) => {
            const stepId = String(step?.id || `step_${idx + 1}`);
            const isActive = stepId === activeId;
            const isValidated = validatedSteps.map((entry: any) => String(entry)).includes(stepId);
            const canClickStep = Boolean(allow_step_click);
            return (
              <Button
                key={stepId}
                type="button"
                color={isActive ? 'primary' : 'secondary'}
                outline={!isActive}
                size="sm"
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
              </Button>
            );
          })}
        </div>
      </CardHeader>
      <CardBody className="p-3 d-grid gap-3">
        <div className="d-flex align-items-center gap-2 flex-wrap">
          <CardTitle className="h5 mb-0">{getLiteral(active?.title || activeId)}</CardTitle>
          <Badge color="secondary" className="a2ui-wizard-badge">Step {activeIndex + 1}/{allSteps.length}</Badge>
        </div>
        {active?.description ? <p className="small text-muted mb-0">{getLiteral(active.description)}</p> : null}
        {active?.content ? <p className="mb-0">{getLiteral(active.content)}</p> : null}
        {show_controls ? (
          <div className="a2ui-wizard-controls mt-2 d-flex align-items-center gap-2">
            <Button
              type="button"
              outline
              color="primary"
              size="sm"
              className="a2ui-button"
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
              <i className="ri-arrow-left-s-line me-1" />
              {getLiteral(prev_label)}
            </Button>
            <Button
              type="button"
              color="primary"
              size="sm"
              className="a2ui-button"
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
              {getLiteral(next_label)}
              <i className="ri-arrow-right-s-line ms-1" />
            </Button>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
};
