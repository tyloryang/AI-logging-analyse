<script setup>
import { computed, useAttrs } from 'vue'
import {
  Bell,
  Calendar,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  BadgeQuestionMark,
  Bot,
  Boxes,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Circle,
  CircleHelp,
  CircleX,
  ClipboardList,
  Clock3,
  Copy,
  Cloud,
  FileDown,
  FilePlus,
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
  HardDrive,
  Inbox,
  Link2,
  KeyRound,
  LayoutGrid,
  Layers3,
  ListFilter,
  Menu,
  Megaphone,
  MessageSquare,
  Monitor,
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
  LogOut,
  RefreshCw,
  Search,
  Settings2,
  Server,
  Save,
  Sun,
  Moon,
  Sparkle,
  Sparkles,
  Star,
  Square,
  SquareDashedMousePointer,
  Terminal,
  TriangleAlert,
  StopCircle,
  Trash2,
  Send,
  Users,
  User,
  Wrench,
  Cpu,
  Database,
  Workflow,
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
  bell: Bell,
  calendar: Calendar,
  bot: Bot,
  boxes: Boxes,
  check: Check,
  chevrondown: ChevronDown,
  chevronright: ChevronRight,
  chevronup: ChevronUp,
  circle: Circle,
  circlehelp: CircleHelp,
  circlex: CircleX,
  clipboardlist: ClipboardList,
  clock3: Clock3,
  copy: Copy,
  cloud: Cloud,
  filedown: FileDown,
  fileplus: FilePlus,
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
  harddrive: HardDrive,
  inbox: Inbox,
  link2: Link2,
  keyround: KeyRound,
  layoutgrid: LayoutGrid,
  layers3: Layers3,
  listfilter: ListFilter,
  menu: Menu,
  megaphone: Megaphone,
  messagesquare: MessageSquare,
  monitor: Monitor,
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
  logout: LogOut,
  refreshcw: RefreshCw,
  search: Search,
  settings2: Settings2,
  server: Server,
  save: Save,
  sun: Sun,
  moon: Moon,
  sparkle: Sparkle,
  sparkles: Sparkles,
  star: Star,
  square: Square,
  squaredashedmousepointer: SquareDashedMousePointer,
  cpu: Cpu,
  database: Database,
  workflow: Workflow,
  terminal: Terminal,
  trianglealert: TriangleAlert,
  stopcircle: StopCircle,
  send: Send,
  trash2: Trash2,
  users: Users,
  user: User,
  wrench: Wrench,
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
