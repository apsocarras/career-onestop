import matplotlib.pyplot as plt 
import matplotlib.patches as mpatches


def plot_bar(data, title, label_column=None, count_column=None, text_buffer=.05, bar_color='skyblue', color_map=None, text_counts=True, display_data=True, legend_map=None): 


    plt.figure(figsize=(10, 6))

    labels = data.index if label_column is None else data[label_column]  
    counts = data.values if count_column is None else data[count_column] 


    bars = plt.barh(labels, counts, color=bar_color)
    plt.title(title)
    plt.gca().invert_yaxis()  # Invert y-axis to have the highest value at the top
    # Add text after the bars to show count 

    # Adding count annotation to each bar
    if text_counts: 
        for bar in bars:
            plt.text(bar.get_width() + text_buffer, bar.get_y() + bar.get_height()/2, 
                        f'{int(bar.get_width())}', 
                        va='center', ha='left', fontsize=10, color='black')
            
    if color_map is not None: 
        # display(data)
        for i, bar in enumerate(bars):
            category = labels[i]
            if category in color_map:
                bar.set_color(color_map[category])
            
   
    if legend_map is not None: 
        legend_handles = [mpatches.Patch(color=color, label=label) for label, color in legend_map.items()]
        plt.legend(handles=legend_handles)
                
    plt.show()

    if display_data: # Note is ignored if not showing the plot, too 
        data_to_display = data.reset_index()
        data_to_display.columns = [col.title().replace('_', ' ') for col in data_to_display.columns]
        data_to_display.index = list(range(1,data.shape[0]+1))
        print(f'Count Column: {data_to_display["Count"].sum()}')
        display(data_to_display)

import matplotlib.pyplot as plt

def plot_pie_chart(dataframe, label_column, count_column, explode_index=None, title='', color_map=None, 
                   legend=False, hide_labels=False, include_counts=False, title_x_pos=.5, title_y_pos=1.05, title_font_dict={}):
    """
    Plot a pie chart from a DataFrame.

    Parameters:
        dataframe (DataFrame): The DataFrame containing the data.
        label_column (str): The name of the column containing the labels for each category.
        count_column (str): The name of the column containing the counts for each category.
        explode_index (int): The index of the category to explode (default is None).

    Returns:
        None
    """
    labels = dataframe[label_column].tolist()
    counts = dataframe[count_column].tolist()

    if color_map:
        colors = [color_map[label] for label in labels]
    else:
        colors = None

    if hide_labels: 
        wedge_labels = [None] * len(labels) 
    else: 
        wedge_labels = labels.copy()


    # Plotting
    plt.figure(figsize=(8, 6))
    explode = [0.1 if i == explode_index else 0 for i in range(len(labels))] if explode_index is not None else None

    plt.pie(counts, labels=wedge_labels, 
            autopct='%1.1f%%', 
            startangle=140, 
            explode=explode, 
            colors=colors)
    plt.title(title,x=title_x_pos, y=title_y_pos, fontdict=title_font_dict)
    plt.axis('equal')

    if legend:
        plt.legend(labels, loc='best')



    plt.show()

# Example usage:
# Assuming 'df' is your DataFrame with the structure similar to the given one.
# plot_pie_chart(df, 'Response', 'Count', explode_index=1)

def plot_histogram(data, bins=10, xlabel='', ylabel='', 
                     title='', grid=False, edgecolor=None, bar_labels=False):
    
    counts, edges, bars = plt.hist(data, bins=bins, color='skyblue', edgecolor=edgecolor)

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)

    if grid: 
        plt.grid(True)
    if bar_labels: 
        plt.bar_label(bars)

    plt.show()