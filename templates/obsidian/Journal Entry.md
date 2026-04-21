---
creationDate: <% tp.date.now("YYYY-MM-DDTHH:mm") %>
type: journal
floor: <% await tp.system.suggester(["Shame","Guilt","Apathy","Grief","Fear","Desire","Anger","Pride","Courage","Neutrality","Willingness","Acceptance","Reason","Love","Joy","Peace"], ["Shame","Guilt","Apathy","Grief","Fear","Desire","Anger","Pride","Courage","Neutrality","Willingness","Acceptance","Reason","Love","Joy","Peace"]) %>
---



---
*Floor: <% tp.frontmatter.floor %> · [[<% ["Shame","Guilt","Apathy","Grief","Fear","Desire","Anger","Pride"].includes(tp.frontmatter.floor) ? "Low Floors" : (["Courage","Neutrality","Willingness","Acceptance","Reason"].includes(tp.frontmatter.floor) ? "Middle Floors" : "High Floors") %>]]*

## Concepts
