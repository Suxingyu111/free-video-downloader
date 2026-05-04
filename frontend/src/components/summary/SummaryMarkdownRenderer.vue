<script setup>
import markdownit from "markdown-it";
import { computed } from "vue";

const props = defineProps({
  markdown: {
    type: String,
    default: ""
  }
});

const markdownRenderer = markdownit({
  html: false,
  linkify: true,
  typographer: true,
  breaks: false
});

markdownRenderer.disable("image");
markdownRenderer.validateLink = (url) => {
  const value = String(url || "").trim().toLowerCase();
  return !/^(javascript|vbscript|data):/.test(value);
};

const defaultLinkOpen = markdownRenderer.renderer.rules.link_open;
markdownRenderer.renderer.rules.link_open = (tokens, index, options, env, self) => {
  tokens[index].attrSet("target", "_blank");
  tokens[index].attrSet("rel", "nofollow noopener noreferrer");
  return defaultLinkOpen ? defaultLinkOpen(tokens, index, options, env, self) : self.renderToken(tokens, index, options);
};

const renderedMarkdown = computed(() => markdownRenderer.render(props.markdown || ""));
</script>

<template>
  <div class="summary-markdown-body" v-html="renderedMarkdown"></div>
</template>
