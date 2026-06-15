import React from 'react';
import { Registry } from '../../renderers';
import { parseStyle } from '../../utils/style';
import { motion } from 'motion/react';
import { 
  evaluateRule, 
  resolveActiveValue, 
  resolveBindings, 
  isObject,
  normalizeActive 
} from '../../renderers/rules';
import { readClientStateValue } from '@/state/clientState';

type RendererProps = {
  surfaceId: string;
  componentId: string;
  surfaces: any;
  dataModel: any;
  stateModel: any;
  sendAction: any;
  setInput: any;
  userRole: string;
  userPermissions: string[];
  pendingActions?: Record<string, number>;
  item?: Record<string, any>;
};

type AnimationSpec = {
  name: string;
  duration?: number;
  delay?: number;
  loop?: number;
  distance?: number;
  fade?: boolean;
  opacity_from?: number;
  opacity_to?: number;
  low?: number;
  high?: number;
};

type StaggerSpec = {
  step: number;
  animation: AnimationSpec;
};

type AnimationContextValue = {
  extraDelayMs: number;
  fallbackAnimation: AnimationSpec | null;
};

const AnimationContext = React.createContext<AnimationContextValue>({
  extraDelayMs: 0,
  fallbackAnimation: null,
});

const normalizeAnimationSpec = (spec: any): AnimationSpec | null => {
  if (typeof spec === 'string') {
    const text = spec.trim();
    if (!text) return null;
    return { name: text };
  }
  if (spec && typeof spec === 'object') {
    const name = String(spec.name ?? spec.type ?? '').trim();
    if (!name) return null;
    return { ...spec, name };
  }
  return null;
};

const normalizeStaggerSpec = (spec: any): StaggerSpec | null => {
  if (spec == null || spec === false) return null;
  if (typeof spec === 'number') {
    return { step: Number(spec), animation: { name: 'fade_in', duration: 220 } };
  }
  if (typeof spec === 'string') {
    const text = spec.trim();
    if (!text) return null;
    return { step: 70, animation: { name: text } };
  }
  if (typeof spec === 'object') {
    const animation = normalizeAnimationSpec(spec.animation ?? spec.preset ?? { name: 'fade_in', duration: 220 }) || {
      name: 'fade_in',
      duration: 220,
    };
    return {
      step: Number(spec.step ?? 70) || 70,
      animation,
    };
  }
  return null;
};

const buildMotionProps = (spec: AnimationSpec | null, extraDelayMs = 0) => {
  if (!spec) return null;

  const duration = Math.max(Number(spec.duration ?? 220) || 220, 1) / 1000;
  const delay = Math.max((Number(spec.delay ?? 0) || 0) + (Number(extraDelayMs) || 0), 0) / 1000;
  const loopCount = Number(spec.loop ?? 1) || 1;
  const repeat = loopCount < 0 ? Infinity : Math.max(loopCount - 1, 0);
  const transitionBase: Record<string, any> = {
    duration,
    delay,
    ease: 'easeOut',
    repeat,
  };
  const opacityFrom = Number(spec.opacity_from ?? 0);
  const opacityTo = Number(spec.opacity_to ?? 1);
  const distance = Number(spec.distance ?? 36) || 36;
  const fade = spec.fade !== false;

  if (spec.name === 'fade' || spec.name === 'fade_in') {
    return {
      initial: { opacity: opacityFrom },
      animate: { opacity: opacityTo },
      transition: transitionBase,
    };
  }

  if (spec.name === 'pulse' || spec.name === 'blink') {
    const low = Number(spec.low ?? (spec.name === 'blink' ? 0.28 : 0.72));
    const high = Number(spec.high ?? 1.0);
    return {
      initial: { opacity: low },
      animate: { opacity: [low, high, 1] },
      transition: { ...transitionBase, ease: 'easeInOut' },
    };
  }

  if (spec.name.startsWith('slide_')) {
    const start: Record<string, any> = {};
    if (spec.name === 'slide_left') start.x = distance;
    if (spec.name === 'slide_right') start.x = -distance;
    if (spec.name === 'slide_up') start.y = distance;
    if (spec.name === 'slide_down') start.y = -distance;
    if (fade) start.opacity = opacityFrom;
    const target: Record<string, any> = { x: 0, y: 0 };
    if (fade) target.opacity = opacityTo;
    return {
      initial: start,
      animate: target,
      transition: transitionBase,
    };
  }

  return null;
};

const normalizePermissions = (value: unknown): string[] => {
  if (!Array.isArray(value)) return [];
  return value.map((entry) => String(entry)).filter(Boolean);
};

const isSuperRole = (role: string): boolean => {
  const normalized = String(role || '').trim().toLowerCase();
  return normalized === 'super' || normalized === 'admin';
};

const resolveAccessContext = (stateModel: any, role: string, permissions: string[]) => {
  const storeRoleValue = readClientStateValue(stateModel, 'global', '/auth/role');
  const storeRole = typeof storeRoleValue === 'string' ? String(storeRoleValue) : '';
  const storePermissions = normalizePermissions(readClientStateValue(stateModel, 'global', '/auth/permissions'));
  const permissionsLoaded = readClientStateValue(stateModel, 'global', '/auth/permissions_loaded') === true;
  const shouldUseStore = permissionsLoaded || storePermissions.length > 0 || Boolean(storeRole && storeRole.toLowerCase() !== 'guest');

  return {
    role: shouldUseStore ? (storeRole || role || 'Guest') : (role || 'Guest'),
    permissions: shouldUseStore ? storePermissions : normalizePermissions(permissions),
  };
};

const hasAccess = (requiredPerms: string[] | string | undefined, role: string, permissions: string[]): boolean => {
  const required = Array.isArray(requiredPerms) ? requiredPerms : requiredPerms ? [requiredPerms] : [];
  if (required.length === 0) return true;
  if (isSuperRole(role)) return true;
  return required.some((perm) => permissions.includes(perm));
};

export const InternalRenderer: React.FC<{
  componentData: any;
  surfaceId: string;
  surfaces: any;
  dataModel: any;
  stateModel: any;
  sendAction: any;
  setInput: any;
  componentId: string;
  userRole: string;
  userPermissions: string[];
  pendingActions?: Record<string, number>;
  item?: Record<string, any>;
}> = ({
  componentData,
  surfaceId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  setInput,
  componentId,
  userRole,
  userPermissions,
  pendingActions,
  item,
}) => {
  if (!componentData || !componentData.component) return null;
  const animationContext = React.useContext(AnimationContext);

  const type = Object.keys(componentData.component)[0];
  const rawProps = componentData.component[type] || {};
  const requiredPermissions = rawProps.required_permissions
    ?? rawProps.permissions
    ?? componentData.required_permissions
    ?? componentData.permissions;
  const access = resolveAccessContext(stateModel, userRole, userPermissions);
  if (!hasAccess(requiredPermissions, access.role, access.permissions)) return null;
  const surfaceModel = dataModel?.[surfaceId] || {};

  const options = {
    surfaceModel,
    stateModel,
    item,
  };

  // Visibility checks (show_if / hide_if) - mirroring desktop behavior
  const showIf = rawProps.show_if ?? componentData.show_if;
  const hideIf = rawProps.hide_if ?? componentData.hide_if;

  if (showIf !== undefined && !evaluateRule(showIf, options, true)) {
    return null;
  }
  if (hideIf !== undefined && evaluateRule(hideIf, options, false)) {
    return null;
  }

  const props = resolveBindings(rawProps, options);

  if (rawProps && Object.prototype.hasOwnProperty.call(rawProps, 'active')) {
    props.active = resolveActiveValue(rawProps.active, options);
  }
  const declaredAnimation = normalizeAnimationSpec(props.animation ?? rawProps?.animation);
  const effectiveAnimation = declaredAnimation || animationContext.fallbackAnimation;
  const motionProps = buildMotionProps(effectiveAnimation, animationContext.extraDelayMs);
  const staggerSpec = normalizeStaggerSpec(props.animation_stagger ?? rawProps?.animation_stagger);
  const { animation: _ignoredAnimation, animation_stagger: _ignoredStagger, ...componentProps } = props;

  const ComponentImpl = Registry[type];
  if (type === 'SurfaceHost') {
    const hostedSurfaceId = typeof props.surface_id === 'string' ? props.surface_id : '';
    const hostedSurface = hostedSurfaceId ? surfaces?.[hostedSurfaceId] : null;
    const hostedRootId = hostedSurface?.rootId || (hostedSurface?.components?.root ? 'root' : '');

    return (
      <div
        data-surface-host-id={hostedSurfaceId || undefined}
        className="d-flex flex-column flex-grow-1 h-100 min-vh-0 min-vw-0 w-100"
        style={parseStyle(props.style)}
      >
        {hostedSurfaceId && hostedRootId ? (
          <A2UIRenderer
            surfaceId={hostedSurfaceId}
            componentId={hostedRootId}
            surfaces={surfaces}
            dataModel={dataModel}
            stateModel={stateModel}
            sendAction={sendAction}
            setInput={setInput}
            userRole={userRole}
            userPermissions={userPermissions}
            pendingActions={pendingActions}
            item={item}
          />
        ) : null}
      </div>
    );
  }
  if (!ComponentImpl) {
    return <div className="a2ui-unknown">Unknown Component: {type}</div>;
  }

  const childrenNode = componentData.children || props.children;

  const renderComponentReference = (
    child: any,
    index: number,
    keyPrefix: string,
  ): React.ReactNode => {
    const node = isObject(child) && child.component ? (
      <InternalRenderer
        key={child.id || `${keyPrefix}_inline_${index}`}
        componentData={child}
        surfaceId={surfaceId}
        surfaces={surfaces}
        dataModel={dataModel}
        stateModel={stateModel}
        sendAction={sendAction}
        setInput={setInput}
        componentId={child.id || `${keyPrefix}_inline_${index}`}
        userRole={userRole}
        userPermissions={userPermissions}
        pendingActions={pendingActions}
        item={item}
      />
    ) : (
      <A2UIRenderer
        key={`${keyPrefix}_${String(child)}`}
        surfaceId={surfaceId}
        componentId={String(child)}
        surfaces={surfaces}
        dataModel={dataModel}
        stateModel={stateModel}
        sendAction={sendAction}
        setInput={setInput}
        userRole={userRole}
        userPermissions={userPermissions}
        pendingActions={pendingActions}
        item={item}
      />
    );

    if (!staggerSpec) {
      return node;
    }

    return (
      <AnimationContext.Provider
        key={`anim_ctx_${componentId}_${keyPrefix}_${index}`}
        value={{
          extraDelayMs: animationContext.extraDelayMs + (Math.max(staggerSpec.step, 0) * index),
          fallbackAnimation: staggerSpec.animation,
        }}
      >
        {node}
      </AnimationContext.Provider>
    );
  };

  const buildReferenceList = (items: any, keyPrefix: string): React.ReactNode[] | null => {
    if (!Array.isArray(items) || items.length === 0) {
      return null;
    }
    return items.map((child, index) => renderComponentReference(child, index, keyPrefix));
  };

  const explicitList = buildReferenceList(childrenNode?.explicitList, 'children');

  const hasHeaderSlots =
    Array.isArray(props.left) ||
    Array.isArray(props.center) ||
    Array.isArray(props.right);

  const headerSlotProps = type === 'Header'
    ? {
        leftExplicitList: buildReferenceList(props.left, 'header_left'),
        centerExplicitList: buildReferenceList(
          hasHeaderSlots ? props.center : childrenNode?.explicitList,
          'header_center',
        ),
        rightExplicitList: buildReferenceList(props.right, 'header_right'),
      }
    : {};

  const renderedNode = (
    <ComponentImpl
      {...componentProps}
      {...headerSlotProps}
      id={componentId}
      ExplicitList={explicitList}
      onAction={(name: string, ctx: any) => sendAction(name, ctx, surfaceId, componentId)}
      setInput={setInput}
      surfaces={surfaces}
      dataModel={dataModel}
      stateModel={stateModel}
      sendAction={sendAction}
      surfaceId={surfaceId}
      userRole={userRole}
      userPermissions={userPermissions}
      pendingActions={pendingActions}
      item={item}
    />
  );

  if (!motionProps) return renderedNode;

  const isStretchComponent =
    componentProps?.stretch === true ||
    componentProps?.stretch === 1 ||
    (typeof componentProps?.stretch === 'number' && componentProps.stretch > 0);

  return (
    <motion.div
      className={isStretchComponent ? 'd-flex flex-column flex-grow-1 h-100 min-vh-0 min-vw-0 w-100' : undefined}
      animate={motionProps.animate}
      initial={motionProps.initial}
      transition={motionProps.transition}
    >
      {renderedNode}
    </motion.div>
  );
};

export const A2UIRenderer: React.FC<RendererProps> = ({
  surfaceId,
  componentId,
  surfaces,
  dataModel,
  stateModel,
  sendAction,
  setInput,
  userRole,
  userPermissions,
  pendingActions,
  item,
}) => {
  const surface = surfaces[surfaceId];
  if (!surface) return null;

  const resolvedComponentId =
    componentId 
      ? (surface.components?.[componentId] ? componentId : '')
      : (surface.rootId || (surface.components?.root ? 'root' : ''));

  const componentData = resolvedComponentId ? surface.components[resolvedComponentId] : null;
  if (!componentData) return null;

  return (
    <InternalRenderer
      componentData={componentData}
      surfaceId={surfaceId}
      surfaces={surfaces}
      dataModel={dataModel}
      stateModel={stateModel}
      sendAction={sendAction}
      setInput={setInput}
      componentId={resolvedComponentId}
      userRole={userRole}
      userPermissions={userPermissions}
      pendingActions={pendingActions}
      item={item}
    />
  );
};

export { resolveBindings, normalizeActive };
