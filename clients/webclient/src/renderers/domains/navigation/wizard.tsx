import React from 'react';
import { parseStyle } from '@/utils/style';
import { emitActionSpec, getLiteral } from '@/renderers/shared';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

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
    return <Card style={parseStyle(style)}><CardContent className="p-4 text-sm text-muted-foreground">No steps configured.</CardContent></Card>;
  }

  return (
    <Card style={parseStyle(style)}>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {allSteps.map((step: any, idx: number) => {
            const stepId = String(step?.id || `step_${idx + 1}`);
            const isActive = stepId === activeId;
            const canClickStep = Boolean(allow_step_click);
            return (
              <Button
                key={stepId}
                type="button"
                variant={isActive ? 'default' : 'outline'}
                size="sm"
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
                {getLiteral(step?.title || stepId)}
              </Button>
            );
          })}
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">{getLiteral(active?.title || activeId)}</CardTitle>
          <Badge variant="secondary">Step {activeIndex + 1}/{allSteps.length}</Badge>
        </div>
        {active?.description ? <p className="text-sm text-muted-foreground">{getLiteral(active.description)}</p> : null}
        {active?.content ? <p className="text-sm">{getLiteral(active.content)}</p> : null}
        {show_controls ? (
          <div className="mt-1 flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
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
              {getLiteral(prev_label)}
            </Button>
            <Button
              type="button"
              size="sm"
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
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};
