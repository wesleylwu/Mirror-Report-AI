export interface HeaderCell {
  label: string;
  value: string;
}

export type HeaderRow = HeaderCell[];

export interface FullWidthRow {
  _full_width: string;
}

export interface TaggedRowStyle {
  bold?: boolean;
  fill?: "none" | "light_gray" | "light_blue" | "light_yellow" | "light_green" | "light_orange";
  align?: "left" | "center" | "right";
}

export interface TaggedRow {
  _tag: string;
  _style?: TaggedRowStyle;
  values: string[];
}

export type TableRow = string[] | FullWidthRow | TaggedRow;

export interface DataCell {
  r: number;
  c: number;
  v: string;
}

export interface ExtractedData {
  title?: string;
  section_header?: string;
  header?: HeaderRow[];
  table?: {
    columns?: string[];
    rows?: TableRow[];
  };
  html?: string;
  data?: DataCell[];
  code?: string;
  filename?: string;
}

export type ExtractedDataPage = ExtractedData;
