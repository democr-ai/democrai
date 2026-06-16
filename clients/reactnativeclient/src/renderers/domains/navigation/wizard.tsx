import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';
import { getLiteral, emitActionSpec } from '../../shared';
import { Badge } from '../feedback/badge';
import { Icon } from '../../../components/a2ui/Icon';

export const Wizard: React.FC<any> = ({
  id,
  steps = [],
  active_step_id,
  validated_steps = [],
  action,
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
  const fallbackId = allSteps[0]?.id;
  const activeId = String(active_step_id || fallbackId || '');
  const baseWizardCtx = {
    ...(wizardId ? { wizard_id: wizardId, target_wizard: wizardId } : {}),
    steps: allSteps,
    active_step_id: activeId,
    validated_steps: validatedSteps,
  };
  const activeIndex = Math.max(0, allSteps.findIndex((entry: any) => String(entry?.id) === activeId));
  const active = allSteps[activeIndex];

  if (!allSteps.length) {
    return (
      <View style={[styles.card, style]}>
        <Text style={styles.emptyText}>No steps configured.</Text>
      </View>
    );
  }

  return (
    <View style={[styles.card, style]}>
      <View style={styles.header}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.stepsScroll}>
          {allSteps.map((step: any, idx: number) => {
            const stepId = String(step?.id || `step_${idx + 1}`);
            const isActive = stepId === activeId;
            const isValidated = validatedSteps.includes(stepId);
            return (
              <TouchableOpacity
                key={stepId}
                disabled={!allow_step_click}
                onPress={() =>
                  emitActionSpec(action, onAction, {
                    ...baseWizardCtx,
                    intent: 'step_click',
                    step_id: stepId,
                    step_index: idx,
                  })
                }
                style={[styles.stepItem, isActive && styles.stepItemActive]}
              >
                {isValidated ? (
                  <Icon name="ri-check-line" size={14} color={isActive ? '#FFFFFF' : '#56D364'} />
                ) : null}
                <Text style={[styles.stepText, isActive && styles.stepTextActive]}>
                  {getLiteral(step?.title || stepId)}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      <View style={styles.content}>
        <View style={styles.titleRow}>
          <Text style={styles.stepTitle}>{getLiteral(active?.title || activeId)}</Text>
          <Badge text={`Step ${activeIndex + 1}/${allSteps.length}`} variant="secondary" />
        </View>
        
        {active?.description ? (
          <Text style={styles.description}>{getLiteral(active.description)}</Text>
        ) : null}
        
        {active?.content ? (
          <Text style={styles.stepContent}>{getLiteral(active.content)}</Text>
        ) : null}

        {show_controls ? (
          <View style={styles.controls}>
            <TouchableOpacity
              disabled={activeIndex <= 0}
              onPress={() =>
                emitActionSpec(action, onAction, {
                  ...baseWizardCtx,
                  intent: 'prev',
                  step_id: activeId,
                  step_index: activeIndex,
                })
              }
              style={[styles.btn, styles.outlineBtn, activeIndex <= 0 && styles.btnDisabled]}
            >
              <Text style={styles.outlineBtnText}>{getLiteral(prev_label)}</Text>
            </TouchableOpacity>
            
            <TouchableOpacity
              disabled={activeIndex >= allSteps.length - 1}
              onPress={() =>
                emitActionSpec(action, onAction, {
                  ...baseWizardCtx,
                  intent: 'next',
                  step_id: activeId,
                  step_index: activeIndex,
                })
              }
              style={[styles.btn, styles.primaryBtn, activeIndex >= allSteps.length - 1 && styles.btnDisabled]}
            >
              <Text style={styles.primaryBtnText}>{getLiteral(next_label)}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#161B22',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#30363D',
    overflow: 'hidden',
    marginVertical: 8,
  },
  header: {
    borderBottomWidth: 1,
    borderBottomColor: '#30363D',
    padding: 8,
    backgroundColor: '#0D1117',
  },
  stepsScroll: {
    gap: 8,
    paddingHorizontal: 4,
  },
  stepItem: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#161B22',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  stepItemActive: {
    backgroundColor: '#6366F1',
    borderColor: '#6366F1',
  },
  stepText: {
    fontSize: 13,
    color: '#C9D1D9',
    fontWeight: '700',
  },
  stepTextActive: {
    color: '#FFFFFF',
  },
  content: {
    padding: 16,
    gap: 12,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stepTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#E6EDF3',
  },
  description: {
    fontSize: 14,
    color: '#8B949E',
    lineHeight: 20,
  },
  stepContent: {
    fontSize: 15,
    color: '#C9D1D9',
    lineHeight: 22,
  },
  controls: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  btn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryBtn: {
    backgroundColor: '#6366F1',
  },
  primaryBtnText: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  outlineBtn: {
    borderWidth: 1,
    borderColor: '#30363D',
    backgroundColor: '#0D1117',
  },
  outlineBtnText: {
    color: '#E6EDF3',
    fontWeight: '600',
  },
  btnDisabled: {
    opacity: 0.5,
  },
  emptyText: {
    padding: 20,
    textAlign: 'center',
    color: '#8B949E',
  },
});
