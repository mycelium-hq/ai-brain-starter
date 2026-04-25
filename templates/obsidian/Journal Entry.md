---
creationDate: <% tp.date.now("YYYY-MM-DDTHH:mm") %>
type: journal
floor: <% await tp.system.suggester(["Disgust","Shame","Embarrassment","Guilt","Apathy","Resignation","Confusion","Loneliness","Boredom","Grief","Disappointment","Hurt","Fear","Frustration","Desire","Anger","Contempt","Pride","Courage","Hope","Neutrality","Willingness","Acceptance","Reason","Trust","Compassion","Humility","Belonging","Love","Gratitude","Excitement","Wonder","Joy","Peace"], ["Disgust","Shame","Embarrassment","Guilt","Apathy","Resignation","Confusion","Loneliness","Boredom","Grief","Disappointment","Hurt","Fear","Frustration","Desire","Anger","Contempt","Pride","Courage","Hope","Neutrality","Willingness","Acceptance","Reason","Trust","Compassion","Humility","Belonging","Love","Gratitude","Excitement","Wonder","Joy","Peace"]) %>
---



---
*Floor: <% tp.frontmatter.floor %> · [[<% ["Disgust","Shame","Embarrassment","Guilt","Apathy","Resignation","Confusion","Loneliness","Boredom","Grief","Disappointment","Hurt","Fear","Frustration","Desire","Anger","Contempt","Pride"].includes(tp.frontmatter.floor) ? "Low Floors" : (["Courage","Hope","Neutrality","Willingness","Acceptance","Reason"].includes(tp.frontmatter.floor) ? "Middle Floors" : "High Floors") %>]]*

## Concepts
