import random
import time


color_theme_templates = [
    "Set the background color to {background_color} and the component color to {component_color}.",
    "Use {background_color} for the background and {component_color} for components.",
    "Apply {background_color} as the background; style all components with {component_color}.",
    "Define the background as {background_color} and components as {component_color}.",
    "Assign {background_color} to the background and {component_color} to the UI elements.",
    "Configure the background color to {background_color}, with components using {component_color}.",
    "Implement {background_color} for the page background and {component_color} for the elements.",
    "Specify {background_color} as the base color and {component_color} for all components.",
    "Style the layout with {background_color} in the background and {component_color} for the interface.",
    "Use {background_color} as the default background and {component_color} for component styling.",
    "Design the site using {background_color} as the background and {component_color} for content blocks.",
    "Apply {background_color} for the layout background and {component_color} for interactive elements.",
    "Choose {background_color} for the background; set all component colors to {component_color}.",
    "Set {background_color} as the body background and use {component_color} for the UI.",
    "Style all pages with a {background_color} background and {component_color} components.",
    "Use {background_color} in the background layer and {component_color} for the component layer.",
    "Establish {background_color} as the main background and {component_color} for the controls.",
    "Set the background to {background_color}, and apply {component_color} to components.",
    "Configure all backgrounds with {background_color} and all components with {component_color}.",
    "Assign {background_color} to body backgrounds and {component_color} to main components.",
    "Use {background_color} for container backgrounds and {component_color} for component visuals.",
    "Set page background to {background_color}; color all components with {component_color}.",
    "Define background as {background_color}; define components with {component_color}.",
    "Implement styling with {background_color} for the background and {component_color} for components.",
    "Apply theme using {background_color} as background and {component_color} for elements.",
    "Color the background using {background_color} and set component styles to {component_color}.",
    "Use {background_color} for the outer layout and {component_color} for UI blocks.",
    "Set primary background to {background_color} and elements to {component_color}.",
    "Choose {background_color} for global background and {component_color} for all components.",
    "Apply {background_color} for layout; use {component_color} for buttons and cards.",
    "Configure your theme with {background_color} as background and {component_color} as component color.",
    "Use a {background_color} background and apply {component_color} to the UI components.",
    "Set overall background to {background_color}, then style components with {component_color}.",
    "Assign {background_color} as the background color and apply {component_color} to all elements.",
    "Initialize the background color with {background_color} and component color with {component_color}.",
    "Apply {background_color} to the canvas background and {component_color} to all visible components.",
    "Declare {background_color} as the global background color and {component_color} for all UI pieces.",
    "Use {background_color} as the screen background and {component_color} for component highlights.",
    "Select {background_color} for layout background and {component_color} for component details.",
    "Set all pages to have a {background_color} background and {component_color} components."
]


def wrap_color_theme(background_color, component_color):
    random.seed(time.time())               # seed with current epoch time
    template_str = random.choice(color_theme_templates)
    return template_str.format(background_color=background_color, component_color=component_color)


if __name__ == "__main__":
    print(wrap_color_theme("black", "white"))