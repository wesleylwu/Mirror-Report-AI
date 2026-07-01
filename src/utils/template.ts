export const fuzzyGet = (
  d: Record<string, string> | undefined,
  key: string,
  cutoff = 0.45,
): string => {
  if (!d) return "";
  if (key in d) return String(d[key]);

  const similarity = (s1: string, s2: string) => {
    let matches = 0;
    for (let i = 0; i < s1.length; i++) {
      if (s2.includes(s1[i])) matches++;
    }
    return matches / Math.max(s1.length, s2.length);
  };

  let bestMatch = "";
  let bestScore = 0;

  for (const k of Object.keys(d)) {
    const score = similarity(key, k);
    if (score > cutoff && score > bestScore) {
      bestScore = score;
      bestMatch = k;
    }
  }

  return bestMatch ? String(d[bestMatch]) : "";
};

export const formatItemCode = (
  text: string,
  opts?: { code_to_type_spaces?: number; type_internal_spaces?: number },
): string => {
  if (!text) return "";
  const codeToTypeSpaces = opts?.code_to_type_spaces ?? 8;
  const typeInternalSpaces = opts?.type_internal_spaces ?? 1;
  const codeToType = "\u00A0".repeat(codeToTypeSpaces);
  const typeInternal = "\u00A0".repeat(typeInternalSpaces);

  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  let codeLine = "";
  let typeToken = "";
  const nameLines: string[] = [];

  const typePat = /^(\d+)\s+(\S+)$/;
  const codePat = /^[A-Za-z][A-Za-z0-9]{3,}/;
  const startTypePat = /^(\d+)\s+(\S+)\s+/;
  const endTypePat = /\s+(\d+)\s+(\S+)\s*$/;

  for (const line of lines) {
    if (codePat.test(line) && !codeLine) {
      const parts = line.split(/\s+/);
      codeLine = parts[0];
      if (parts.length > 1) {
        const remainder = parts.slice(1).join(" ").trim();
        const startMatch = startTypePat.exec(remainder);
        if (startMatch && (startMatch[1] + startMatch[2]).length <= 12) {
          typeToken = `${startMatch[1]}${typeInternal}${startMatch[2]}`;
          const namePart = remainder.substring(startMatch[0].length).trim();
          if (namePart) nameLines.push(namePart);
        } else {
          const endMatch = endTypePat.exec(remainder);
          if (endMatch && (endMatch[1] + endMatch[2]).length <= 12) {
            typeToken = `${endMatch[1]}${typeInternal}${endMatch[2]}`;
            const namePart = remainder.substring(0, endMatch.index).trim();
            if (namePart) nameLines.push(namePart);
          } else {
            nameLines.push(remainder);
          }
        }
      }
    } else {
      const typeMatch = typePat.exec(line);
      if (typeMatch && line.length <= 12) {
        typeToken = `${typeMatch[1]}${typeInternal}${typeMatch[2]}`;
      } else {
        nameLines.push(line);
      }
    }
  }

  const firstLine = typeToken
    ? `${codeLine}${codeToType}${typeToken}`
    : codeLine;
  const rest = nameLines.join("\n");
  return rest ? `${firstLine}\n${rest}` : firstLine;
};

export const parseFormattedItemCode = (text: string) => {
  if (!text) return { code: "", typeToken: "", name: "" };
  const lines = text.split("\n");
  const firstLine = lines[0] || "";
  const nameLine = lines.slice(1).join("\n") || "";

  const parts = firstLine.split(/\u00A0{2,}|\s{2,}/);
  const code = parts[0] || "";
  const typeToken = (parts[1] || "").trim();

  return { code, typeToken, name: nameLine };
};
