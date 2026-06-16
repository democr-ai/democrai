import { View } from 'react-native';
import { Row, Column, FlexContainer, Flow } from './domains/layout/containers';
import { Text, Title } from './domains/text/typography';
import { Button } from './domains/actions/button';
import { VerticalButton } from './domains/actions/vertical_button';
import { Sidebar } from './domains/layout/sidebar';
import { Markdown } from './domains/text/markdown';
import { Card, ContentArea, ScrollArea } from './domains/layout/content';
import { Header } from './domains/layout/header';
import { Tabs } from './domains/layout/tabs';
import { Dialog, Grid, Splitter } from './domains/layout/advanced';

import { Alert } from './domains/feedback/alert';
import { Badge } from './domains/feedback/badge';
import { Progress } from './domains/feedback/progress';
import { Skeleton } from './domains/feedback/skeleton';
import { DropdownMenu } from './domains/feedback/dropdown_menu';

import { TextField } from './domains/forms/text_field';
import { TextArea } from './domains/forms/textarea';
import { Checkbox } from './domains/forms/checkbox';
import { RadioGroup } from './domains/forms/radio_group';
import { Select } from './domains/forms/select';
import { Switch } from './domains/forms/switch';
import { Toggle } from './domains/forms/toggle';
import { Attachment } from './domains/forms/attachment';
import { Form } from './domains/forms/form';
import { DatePicker } from './domains/forms/date_picker';
import { Combobox } from './domains/forms/combobox';
import { Calendar } from './domains/forms/calendar';
import { FolderSelector } from './domains/forms/folder_selector';
import { EditableList } from './domains/forms/editable_list';
import { TagsInput } from './domains/forms/tags_input';
import { AudioRecorder } from './domains/forms/audio_recorder';

import { Image } from './domains/media/image';
import { Audio } from './domains/media/audio';
import { Video } from './domains/media/video';
import { QRCode } from './domains/media/qr_code';

import { Accordion } from './domains/navigation/accordion';
import { Collapsible } from './domains/navigation/collapsible';
import { Wizard } from './domains/navigation/wizard';
import { Breadcrumb } from './domains/navigation/breadcrumb';
import { TreeView } from './domains/navigation/tree_view';

import { Composer } from './domains/conversation/composer';
import { MessageItem } from './domains/conversation/message_item';
import { MessageList } from './domains/conversation/message_list';
import { Suggestions } from './domains/conversation/suggestions';
import { AttachmentPreview } from './domains/conversation/attachment_preview';
import { PdfViewer } from './domains/conversation/pdf_viewer';
import { Thread } from './domains/conversation/thread';
import { ThreadList } from './domains/conversation/thread_list';
import { ScrollToBottomButton } from './domains/conversation/scroll_to_bottom_button';

import { Descriptions } from './domains/data/descriptions';
import { DataTable } from './domains/data/data_table';
import { Carousel } from './domains/data/carousel';
import { List } from './domains/data/list';
import {
  Chart, Diagram, CodeDiff, Gantt, GitGraph, SequenceDiagram, Workflow,
  DashboardWidget, GridDropZone,
} from './domains/data/visuals';
import { StreamBinding } from './domains/runtime/stream_binding';
import { BackgroundTask } from './domains/tasks/background_task';

import { ClientTag } from './domains/shell/client_tag';

export const Registry: Record<string, React.FC<any>> = {
  AttachmentPreview,
  BackgroundTask,
  Accordion,
  Alert,
  Audio,
  AudioRecorder,
  Badge,
  Breadcrumb,
  Button,
  Card,
  Carousel,
  Chart,
  Checkbox,
  ClientTag,
  CodeDiff,
  Collapsible,
  Column,
  FlexContainer,
  Flow,
  Composer,
  DataTable,
  Descriptions,
  Diagram,
  Dialog,
  Form,
  Calendar,
  Combobox,
  DashboardWidget,
  DatePicker,
  DropdownMenu,
  EditableList,
  FolderSelector,
  Gantt,
  GitGraph,
  Grid,
  GridDropZone,
  Header,
  Image,
  List,
  Markdown,
  MessageItem,
  MessageList,
  PdfViewer,
  Progress,
  QRCode,
  RadioGroup,
  Row,
  ScrollArea,
  Select,
  SequenceDiagram,
  Sidebar,
  Skeleton,
  Splitter,
  StreamBinding,
  ScrollToBottomButton,
  Suggestions,
  Switch,
  Tabs,
  Text,
  TextField,
  Title,
  TagsInput,
  Toggle,
  TreeView,
  TextArea,
  Thread,
  ThreadList,
  Attachment,
  VerticalButton,
  Video,
  Wizard,
  Workflow,
  // Fallbacks for web components that might be sent by the backend
  div: Column,
  span: Text,
  main: ScrollArea,
  header: Header,
  footer: View as any,
  section: Column,
  article: Column,
  nav: Column,
  aside: Sidebar,
  ContentArea,
  // Case-insensitive fallbacks for common types
  column: Column,
  row: Row,
  text: Text,
  title: Title,
  button: Button,
  card: Card,
  image: Image,
  form: Form,
  input: TextField,
  textarea: TextArea,
  select: Select,
  tags: TagsInput,
  tags_input: TagsInput,
  tagsinput: TagsInput,
  editable_list: EditableList,
  editablelist: EditableList,
  checkbox: Checkbox,
  switch: Switch,
  badge: Badge,
  alert: Alert,
  audio_recorder: AudioRecorder,
  audiorecorder: AudioRecorder,
  progress: Progress,
  skeleton: Skeleton,
  tabs: Tabs,
  accordion: Accordion,
  collapsible: Collapsible,
  wizard: Wizard,
};
