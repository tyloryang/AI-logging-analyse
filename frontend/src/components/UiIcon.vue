<script setup>
import { computed, useAttrs } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BadgeQuestionMark,
  Bot,
  Boxes,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Circle,
  CircleHelp,
  ClipboardList,
  Clock3,
  Copy,
  FileSearch,
  FileText,
  Filter,
  Folder,
  Gauge,
  GitBranch,
  Globe,
  GripVertical,
  HelpCircle,
  History,
  Home,
  Inbox,
  KeyRound,
  LayoutGrid,
  Layers3,
  ListFilter,
  Menu,
  MessageSquare,
  MousePointer2,
  MoveDown,
  MoveRight,
  NotebookText,
  PanelBottomOpen,
  PanelRight,
  PanelRightOpen,
  PanelTopOpen,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  Sparkle,
  Sparkles,
  Square,
  SquareDashedMousePointer,
  Terminal,
  TriangleAlert,
  StopCircle,
  Waypoints,
  X,
} from '@lucide/vue'

defineOptions({
  inheritAttrs: false,
})

const props = defineProps({
  name: {
    type: String,
    required: true,
  },
  size: {
    type: [Number, String],
    default: 18,
  },
  strokeWidth: {
    type: [Number, String],
    default: 2,
  },
  absoluteStrokeWidth: {
    type: Boolean,
    default: false,
  },
  label: {
    type: String,
    default: '',
  },
})

const attrs = useAttrs()

const ICONS = {
  alerttriangle: AlertTriangle,
  arrowleft: ArrowLeft,
  arrowright: ArrowRight,
  arrowupright: ArrowUpRight,
  badgequestionmark: BadgeQuestionMark,
  bot: Bot,
  boxes: Boxes,
  chevrondown: ChevronDown,
  chevronright: ChevronRight,
  chevronup: ChevronUp,
  circle: Circle,
  circlehelp: CircleHelp,
  clipboardlist: ClipboardList,
  clock3: Clock3,
  copy: Copy,
  filesearch: FileSearch,
  filetext: FileText,
  filter: Filter,
  folder: Folder,
  gauge: Gauge,
  gitbranch: GitBranch,
  globe: Globe,
  gripvertical: GripVertical,
  helpcircle: HelpCircle,
  history: History,
  home: Home,
  inbox: Inbox,
  keyround: KeyRound,
  layoutgrid: LayoutGrid,
  layers3: Layers3,
  listfilter: ListFilter,
  menu: Menu,
  messagesquare: MessageSquare,
  mousepointer2: MousePointer2,
  movedown: MoveDown,
  moveright: MoveRight,
  notebooktext: NotebookText,
  panelbottomopen: PanelBottomOpen,
  panelright: PanelRight,
  panelrightopen: PanelRightOpen,
  paneltopopen: PanelTopOpen,
  pencil: Pencil,
  plus: Plus,
  refreshcw: RefreshCw,
  search: Search,
  settings2: Settings2,
  sparkle: Sparkle,
  sparkles: Sparkles,
  square: Square,
  squaredashedmousepointer: SquareDashedMousePointer,
  terminal: Terminal,
  trianglealert: TriangleAlert,
  stopcircle: StopCircle,
  waypoints: Waypoints,
  x: X,
}

const iconKey = computed(() => normalizeIconName(props.name))
const iconComponent = computed(() => ICONS[iconKey.value] || CircleHelp)
const iconAttrs = computed(() => {
  const passthrough = { ...attrs }
  delete passthrough.class
  return {
    ...passthrough,
    ...(props.label
      ? { role: 'img', 'aria-label': props.label }
      : { 'aria-hidden': 'true' }),
    focusable: 'false',
  }
})

function normalizeIconName(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
}
</script>

<template>
  <component
    :is="iconComponent"
    :class="['ui-icon', attrs.class]"
    :size="size"
    :stroke-width="strokeWidth"
    :absolute-stroke-width="absoluteStrokeWidth"
    v-bind="iconAttrs"
  />
</template>
