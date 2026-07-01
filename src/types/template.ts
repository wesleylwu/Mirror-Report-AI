export interface BorderSpec {
  top?: string | null;
  bottom?: string | null;
  left?: string | null;
  right?: string | null;
}

export interface FontSpec {
  bold?: boolean;
  size?: number;
}

export interface AlignSpec {
  h?: "center" | "right" | "left";
  v?: "center" | "bottom" | "top";
  wrap?: boolean;
}

export interface CellSpec {
  fixed?: boolean;
  value?: string;
  key?: string;
  col: number;
  end_col: number;
  border?: BorderSpec;
  align?: AlignSpec;
  font?: FontSpec;
  value_part?: "main" | "tail";
  title_part?: "left" | "center" | "right";
  concat_keys?: string[];
  label_prefix?: boolean;
}

export interface HeaderRowSpec {
  height?: number;
  cells: CellSpec[];
}

export interface ColumnSpec {
  key?: string;
  format?: string;
  format_options?: {
    code_to_type_spaces?: number;
    type_internal_spaces?: number;
  };
  col: number;
  end_col: number;
  border?: BorderSpec;
  first_row_border?: BorderSpec;
  align?: AlignSpec;
  font?: FontSpec;
  col_index?: number;
  concat_col_index?: number;
  concat_sep?: string;
  fallback_col_indices?: number[];
  split_rows?: boolean;
}

export interface DataRowsSpec {
  columns: ColumnSpec[];
  count?: number;
  row_height?: number;
}

export interface FooterSpec {
  height?: number;
  cells: CellSpec[];
}

export interface MatchedTemplate {
  column_widths?: Record<string, number>;
  header?: HeaderRowSpec[];
  col_headers?: {
    row_heights?: number[];
    cells: CellSpec[];
  };
  data_rows?: DataRowsSpec;
  footer?: FooterSpec;
}

export interface ExtractedData {
  title?: string;
  section_header?: string;
  header?: Record<string, string>;
  table?: {
    columns?: string[];
    rows?: Record<string, string>[];
  };
}

export type ExtractedDataPage = ExtractedData;
