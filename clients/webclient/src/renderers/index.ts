import { Button } from './domains/actions/button';
import { VerticalButton } from './domains/actions/vertical_button';

import { Composer } from './domains/conversation/composer';
import { AttachmentPreview } from './domains/conversation/attachment_preview';
import { MessageItem } from './domains/conversation/message_item';
import { MessageList } from './domains/conversation/message_list';
import { PdfViewer } from './domains/conversation/pdf_viewer';
import { ScrollToBottomButton } from './domains/conversation/scroll_to_bottom_button';
import { Suggestions } from './domains/conversation/suggestions';
import { Thread } from './domains/conversation/thread';
import { ThreadList } from './domains/conversation/thread_list';

import { DashboardWidget } from './domains/dashboard/dashboard_widget';
import { GridDropZone } from './domains/dashboard/grid_drop_zone';

import { Carousel } from './domains/data/carousel';
import { Chart } from './domains/data/chart';
import { CodeDiff } from './domains/data/code_diff';
import { DataTable } from './domains/data/data_table';
import { Descriptions } from './domains/data/descriptions';
import { Diagram } from './domains/data/diagram';
import { Gantt } from './domains/data/gantt';
import { GitGraph } from './domains/data/git_graph';
import { List } from './domains/data/list';
import { SequenceDiagram } from './domains/data/sequence_diagram';
import { Workflow } from './domains/data/workflow';

import { Alert } from './domains/feedback/alert';
import { Badge } from './domains/feedback/badge';
import { DropdownMenu } from './domains/feedback/dropdown_menu';
import { Progress } from './domains/feedback/progress';
import { Skeleton } from './domains/feedback/skeleton';

import { Calendar } from './domains/forms/calendar';
import { Checkbox } from './domains/forms/checkbox';
import { Combobox } from './domains/forms/combobox';
import { DatePicker } from './domains/forms/date_picker';
import { EditableList } from './domains/forms/editable_list';
import { FolderSelector } from './domains/forms/folder_selector';
import { Form } from './domains/forms/form';
import { RadioGroup } from './domains/forms/radio_group';
import { Select } from './domains/forms/select';
import { Switch } from './domains/forms/switch';
import { TagsInput } from './domains/forms/tags_input';
import { TextField } from './domains/forms/text_field';
import { TextArea } from './domains/forms/textarea';
import { Toggle } from './domains/forms/toggle';
import { Attachment } from './domains/forms/attachment';

import { Card } from './domains/layout/card';
import { Column } from './domains/layout/column';
import { ContentArea } from './domains/layout/content_area';
import { FlexContainer } from './domains/layout/flex_container';
import { Flow } from './domains/layout/flow';
import { Dialog } from './domains/layout/dialog';
import { Grid } from './domains/layout/grid';
import { Header } from './domains/layout/header';
import { Row } from './domains/layout/row';
import { ScrollArea } from './domains/layout/scroll_area';
import { Sidebar } from './domains/layout/sidebar';
import { Splitter } from './domains/layout/splitter';
import { SurfaceHost } from './domains/layout/surface_host';
import { Tabs } from './domains/layout/tabs';

import { Audio } from './domains/media/audio';
import { Image } from './domains/media/image';
import { QRCode } from './domains/media/qr_code';
import { Video } from './domains/media/video';

import { Accordion } from './domains/navigation/accordion';
import { Breadcrumb } from './domains/navigation/breadcrumb';
import { Collapsible } from './domains/navigation/collapsible';
import { TreeView } from './domains/navigation/tree_view';
import { Wizard } from './domains/navigation/wizard';

import { ClientTag } from './domains/shell/client_tag';

import { StreamBinding } from './domains/runtime/stream_binding';

import { BackgroundTaskCard } from './domains/tasks/background_task_card';

import { Markdown } from './domains/text/markdown';
import { Text } from './domains/text/text';
import { Title } from './domains/text/title';

export const Registry: Record<string, React.FC<any>> = {
  AttachmentPreview,
  BackgroundTask: BackgroundTaskCard,
  Accordion,
  Alert,
  Audio,
  Badge,
  Breadcrumb,
  Button,
  Calendar,
  Card,
  Carousel,
  Chart,
  Checkbox,
  ClientTag,
  CodeDiff,
  Collapsible,
  Column,
  Combobox,
  FlexContainer,
  Flow,
  Composer,
  ContentArea,
  DashboardWidget,
  DataTable,
  DatePicker,
  Diagram,
  Descriptions,
  Dialog,
  DropdownMenu,
  EditableList,
  FolderSelector,
  Form,
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
  ScrollToBottomButton,
  Select,
  SequenceDiagram,
  Workflow,
  Sidebar,
  Skeleton,
  Splitter,
  StreamBinding,
  Suggestions,
  SurfaceHost,
  Switch,
  Tabs,
  TagsInput,
  Text,
  TextField,
  Thread,
  ThreadList,
  Title,
  Toggle,
  TextArea,
  Attachment,
  TreeView,
  VerticalButton,
  Video,
  Wizard,
};
