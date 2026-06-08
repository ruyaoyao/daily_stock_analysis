declare module 'opencc-js' {
  export interface ConverterOptions {
    from?: string;
    to?: string;
  }
  export function Converter(options: ConverterOptions): (text: string) => string;
  export function CustomConverter(table: Array<[string, string]>): (text: string) => string;
}
